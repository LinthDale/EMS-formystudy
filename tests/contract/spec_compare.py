"""Pure comparison functions: committed openapi.yml subset vs FastAPI runtime schema.

Every function takes immutable inputs and returns a NEW list of human-readable
drift findings (empty list == no drift). Nothing here mutates its arguments.

Checked dimensions (api-contract-governance §5 "runtime drift test"):
  1. path set            (both directions: undocumented route / dead spec path)
  2. methods per path
  3. query params per operation: names, required flag, enum allowlists, min/max
  4. 2xx status codes + the $ref'd response schema (incl. array-of-$ref)
  5. requestBody schema $ref
  6. component schemas: property names, required set, property enums

Deliberately NOT checked (documented gaps, not silent ones):
  - 4xx/5xx documentation: the committed spec documents handler behaviour
    (401/403/409/429/503) that FastAPI cannot auto-derive; comparing would
    always produce false drift.
  - header params / securitySchemes: the spec models X-API-Key as a security
    scheme while the app implements it as a dependency + Header param.
  - property *types*: OpenAPI 3.0-style `nullable` in the committed file vs
    pydantic v2 `anyOf [.., null]` cannot be compared textually; names,
    required-ness and enums are the load-bearing contract for the TS client.
"""
from __future__ import annotations

from .spec_loader import operations

_NULL_TYPE = "null"


# ── schema normalization ───────────────────────────────────────────────────────

def resolve_ref(spec: dict, node: dict) -> dict:
    """Follow a local '#/components/schemas/X' $ref (one level; cycles impossible here)."""
    ref = node.get("$ref")
    if not ref:
        return node
    name = ref.rsplit("/", 1)[-1]
    return spec.get("components", {}).get("schemas", {}).get(name, {})


def normalize_schema(spec: dict, schema: dict | None) -> dict:
    """Resolve $ref and merge anyOf non-null branches so that pydantic-v2 optional
    fields ({anyOf: [{type: integer, ...}, {type: null}]}) and plain 3.0-style
    schemas ({type: integer, nullable: true}) normalize to a comparable dict."""
    if not schema:
        return {}
    schema = resolve_ref(spec, schema)
    branches = schema.get("anyOf")
    if not branches:
        return schema
    merged: dict = {k: v for k, v in schema.items() if k != "anyOf"}
    for branch in branches:
        branch = resolve_ref(spec, branch)
        if branch.get("type") == _NULL_TYPE:
            continue
        merged = {**branch, **merged}
    return merged


def ref_name(node: dict | None) -> str | None:
    if not node or "$ref" not in node:
        return None
    return node["$ref"].rsplit("/", 1)[-1]


# ── extraction helpers ─────────────────────────────────────────────────────────

def query_params(spec: dict, path_item: dict, op: dict) -> dict[str, dict]:
    """name → {required, schema} for query params (path-level + operation-level)."""
    out: dict[str, dict] = {}
    for raw in list(path_item.get("parameters", [])) + list(op.get("parameters", [])):
        param = resolve_ref(spec, raw)
        if param.get("in") == "query":
            out[param["name"]] = {
                "required": bool(param.get("required", False)),
                "schema": normalize_schema(spec, param.get("schema")),
            }
    return out


def success_codes(op: dict) -> set[str]:
    return {str(c) for c in op.get("responses", {}) if str(c).startswith("2")}


def response_schema_id(op: dict, code: str) -> tuple[str, str]:
    """('object'|'array'|'none'|'inline', schema-name) of a response's JSON body."""
    response = op.get("responses", {}).get(code) or op.get("responses", {}).get(int(code), {})
    schema = (response or {}).get("content", {}).get("application/json", {}).get("schema")
    return _schema_id(schema)


def request_schema_id(op: dict) -> tuple[str, str]:
    schema = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
    return _schema_id(schema)


def _schema_id(schema: dict | None) -> tuple[str, str]:
    if not schema:
        return ("none", "")
    name = ref_name(schema)
    if name:
        return ("object", name)
    if schema.get("type") == "array":
        item_name = ref_name(schema.get("items"))
        if item_name:
            return ("array", item_name)
    return ("inline", "")


def collect_schema_refs(spec: dict, path_subset: dict[str, dict]) -> set[str]:
    """All component-schema names referenced (transitively) by the given paths'
    requestBodies and 2xx responses."""
    pending: list[str] = []
    for item in path_subset.values():
        for op in operations(item).values():
            for kind, name in [request_schema_id(op)] + [
                response_schema_id(op, c) for c in success_codes(op)
            ]:
                if kind in ("object", "array"):
                    pending.append(name)
    seen: set[str] = set()
    components = spec.get("components", {}).get("schemas", {})
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(_nested_refs(components.get(name, {})))
    return seen


def _nested_refs(node) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        name = ref_name(node)
        if name:
            refs.append(name)
        for value in node.values():
            refs.extend(_nested_refs(value))
    elif isinstance(node, list):
        for value in node:
            refs.extend(_nested_refs(value))
    return refs


# ── comparison passes (each returns a new findings list) ───────────────────────

def compare_paths(committed: dict[str, dict], runtime_paths: dict[str, dict]) -> list[str]:
    missing = sorted(set(committed) - set(runtime_paths))
    extra = sorted(set(runtime_paths) - set(committed))
    findings = [f"path documented in openapi.yml but absent from runtime app: {p}" for p in missing]
    findings += [f"runtime route not documented in openapi.yml: {p}" for p in extra]
    return findings


def compare_methods(committed: dict[str, dict], runtime_paths: dict[str, dict]) -> list[str]:
    findings: list[str] = []
    for path in sorted(set(committed) & set(runtime_paths)):
        spec_methods = set(operations(committed[path]))
        run_methods = set(operations(runtime_paths[path]))
        for m in sorted(spec_methods - run_methods):
            findings.append(f"{m.upper()} {path}: documented in openapi.yml but not implemented")
        for m in sorted(run_methods - spec_methods):
            findings.append(f"{m.upper()} {path}: implemented but not documented in openapi.yml")
    return findings


def compare_query_params(
    committed_spec: dict, committed: dict[str, dict],
    runtime_spec: dict, runtime_paths: dict[str, dict],
) -> list[str]:
    findings: list[str] = []
    for path, method, spec_op, run_op in _shared_ops(committed, runtime_paths):
        where = f"{method.upper()} {path}"
        spec_params = query_params(committed_spec, committed[path], spec_op)
        run_params = query_params(runtime_spec, runtime_paths[path], run_op)
        for name in sorted(set(spec_params) - set(run_params)):
            findings.append(f"{where}: query param '{name}' documented but not accepted by runtime")
        for name in sorted(set(run_params) - set(spec_params)):
            findings.append(f"{where}: runtime accepts undocumented query param '{name}'")
        for name in sorted(set(spec_params) & set(run_params)):
            findings += _compare_one_param(where, name, spec_params[name], run_params[name])
    return findings


def _compare_one_param(where: str, name: str, spec_p: dict, run_p: dict) -> list[str]:
    findings: list[str] = []
    if spec_p["required"] != run_p["required"]:
        findings.append(
            f"{where}: query param '{name}' required mismatch "
            f"(spec={spec_p['required']}, runtime={run_p['required']})")
    spec_schema, run_schema = spec_p["schema"], run_p["schema"]
    if "enum" in spec_schema and set(spec_schema["enum"]) != set(run_schema.get("enum", [])):
        findings.append(
            f"{where}: query param '{name}' enum mismatch "
            f"(spec={sorted(spec_schema['enum'])}, runtime={sorted(run_schema.get('enum', []))})")
    for bound in ("minimum", "maximum"):
        if bound in spec_schema and spec_schema[bound] != run_schema.get(bound):
            findings.append(
                f"{where}: query param '{name}' {bound} mismatch "
                f"(spec={spec_schema[bound]}, runtime={run_schema.get(bound)})")
    return findings


def compare_success_responses(committed: dict[str, dict], runtime_paths: dict[str, dict]) -> list[str]:
    findings: list[str] = []
    for path, method, spec_op, run_op in _shared_ops(committed, runtime_paths):
        where = f"{method.upper()} {path}"
        spec_2xx, run_2xx = success_codes(spec_op), success_codes(run_op)
        if spec_2xx != run_2xx:
            findings.append(
                f"{where}: success status codes mismatch "
                f"(spec={sorted(spec_2xx)}, runtime={sorted(run_2xx)})")
            continue
        for code in sorted(spec_2xx):
            spec_id, run_id = response_schema_id(spec_op, code), response_schema_id(run_op, code)
            if spec_id != run_id:
                findings.append(
                    f"{where} {code}: response schema mismatch (spec={spec_id}, runtime={run_id})")
    return findings


def compare_request_bodies(committed: dict[str, dict], runtime_paths: dict[str, dict]) -> list[str]:
    findings: list[str] = []
    for path, method, spec_op, run_op in _shared_ops(committed, runtime_paths):
        spec_id, run_id = request_schema_id(spec_op), request_schema_id(run_op)
        if spec_id != run_id:
            findings.append(
                f"{method.upper()} {path}: requestBody schema mismatch "
                f"(spec={spec_id}, runtime={run_id})")
    return findings


def compare_component_schemas(committed_spec: dict, runtime_spec: dict, names: set[str]) -> list[str]:
    findings: list[str] = []
    spec_schemas = committed_spec.get("components", {}).get("schemas", {})
    run_schemas = runtime_spec.get("components", {}).get("schemas", {})
    for name in sorted(names):
        if name not in spec_schemas:
            findings.append(f"schema '{name}' referenced but missing from openapi.yml components")
            continue
        if name not in run_schemas:
            findings.append(f"schema '{name}' documented but missing from runtime components")
            continue
        findings += _compare_one_schema(committed_spec, runtime_spec,
                                        name, spec_schemas[name], run_schemas[name])
    return findings


def _compare_one_schema(committed_spec: dict, runtime_spec: dict,
                        name: str, spec_s: dict, run_s: dict) -> list[str]:
    findings: list[str] = []
    spec_props, run_props = spec_s.get("properties", {}), run_s.get("properties", {})
    for prop in sorted(set(spec_props) - set(run_props)):
        findings.append(f"schema '{name}': field '{prop}' documented but absent from runtime model")
    for prop in sorted(set(run_props) - set(spec_props)):
        findings.append(f"schema '{name}': runtime model returns undocumented field '{prop}'")
    spec_req, run_req = set(spec_s.get("required", [])), set(run_s.get("required", []))
    if spec_req != run_req:
        findings.append(
            f"schema '{name}': required mismatch (spec={sorted(spec_req)}, runtime={sorted(run_req)})")
    for prop in sorted(set(spec_props) & set(run_props)):
        spec_field = normalize_schema(committed_spec, spec_props[prop])
        run_field = normalize_schema(runtime_spec, run_props[prop])
        if "enum" in spec_field and set(spec_field["enum"]) != set(run_field.get("enum", [])):
            findings.append(
                f"schema '{name}': field '{prop}' enum mismatch "
                f"(spec={sorted(spec_field['enum'])}, runtime={sorted(run_field.get('enum', []))})")
    return findings


def _shared_ops(committed: dict[str, dict], runtime_paths: dict[str, dict]):
    for path in sorted(set(committed) & set(runtime_paths)):
        spec_ops, run_ops = operations(committed[path]), operations(runtime_paths[path])
        for method in sorted(set(spec_ops) & set(run_ops)):
            yield path, method, spec_ops[method], run_ops[method]


# ── single aggregate entry point (used by the test and by meta-tests) ──────────

def diff_contract(committed_spec: dict, runtime_spec: dict, committed_subset: dict[str, dict]) -> list[str]:
    """All drift findings between the committed device-service subset and the runtime app."""
    runtime_paths = runtime_spec.get("paths", {})
    findings = compare_paths(committed_subset, runtime_paths)
    findings += compare_methods(committed_subset, runtime_paths)
    findings += compare_query_params(committed_spec, committed_subset, runtime_spec, runtime_paths)
    findings += compare_success_responses(committed_subset, runtime_paths)
    findings += compare_request_bodies(committed_subset, runtime_paths)
    names = collect_schema_refs(committed_spec, committed_subset) | collect_schema_refs(
        runtime_spec, {p: i for p, i in runtime_paths.items() if p in committed_subset})
    findings += compare_component_schemas(committed_spec, runtime_spec, names)
    return findings
