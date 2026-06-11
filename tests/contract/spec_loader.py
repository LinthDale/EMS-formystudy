"""Loaders for the two sides of the API contract drift check (PRD-0005 §13.2, R-012/R2).

Committed side : api/openapi.yml — the single source of truth (api-contract-governance §1).
Runtime side   : device_service.main.create_app().openapi() — what FastAPI actually serves.

No Docker and no network needed: the ASGI app is imported, never started (lifespan
does not run, so no DB / MQTT / LLM access happens).

EMS_OPENAPI_SPEC_PATH overrides the committed-spec path. It exists so the drift
gate itself can be exercised against a deliberately mutated COPY of the spec
(see test_openapi_drift.py meta-tests) without ever editing api/openapi.yml.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

SPEC_PATH_ENV = "EMS_OPENAPI_SPEC_PATH"
DEVICE_SERVICE_TAG = "Device Service"
_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def repo_root() -> Path:
    """EMS repo root (tests/contract/ → two levels up)."""
    return Path(__file__).resolve().parents[2]


def committed_spec_path() -> Path:
    override = os.environ.get(SPEC_PATH_ENV)
    return Path(override) if override else repo_root() / "api" / "openapi.yml"


def load_committed_spec() -> dict:
    """Parse the committed OpenAPI document; fail fast on a missing/invalid file."""
    path = committed_spec_path()
    if not path.is_file():
        raise FileNotFoundError(f"committed OpenAPI spec not found at {path}")
    with path.open(encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    if not isinstance(spec, dict) or "paths" not in spec or "info" not in spec:
        raise ValueError(f"{path} is not a valid OpenAPI document (missing 'paths'/'info')")
    return spec


def load_runtime_spec() -> dict:
    """Build the device-service ASGI app and return its generated OpenAPI schema.

    Import is deferred so spec_loader stays importable in environments without
    the device-service dependencies (the failure then points at the right line).
    """
    from device_service.main import create_app  # sys.path provided by tests/conftest.py

    return create_app().openapi()


def operations(path_item: dict) -> dict[str, dict]:
    """HTTP-method operations of a path item (drops 'parameters', 'servers', ...)."""
    return {m: op for m, op in path_item.items() if m in _HTTP_METHODS}


def device_service_subset(committed_spec: dict) -> dict[str, dict]:
    """Paths of the committed spec that belong to the device-service (by tag).

    The committed openapi.yml also documents the Simulator / PostgREST / Grafana
    surfaces, which are NOT part of the device-service ASGI app — drift for those
    cannot be checked by importing the app, so they are excluded here.
    """
    subset: dict[str, dict] = {}
    for path, item in committed_spec.get("paths", {}).items():
        ops = operations(item)
        if any(DEVICE_SERVICE_TAG in op.get("tags", []) for op in ops.values()):
            subset[path] = item
    return subset
