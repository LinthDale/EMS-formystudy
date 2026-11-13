"""API version-bump gate (api-contract-governance §2/§5 "version check" + §6 CHANGELOG).

Rule: if api/openapi.yml changed vs the merge base, then
  1. info.version MUST be bumped (strictly greater semver), and
  2. api/CHANGELOG.md MUST be updated, and
  3. the updated CHANGELOG MUST contain a '## <new version>' entry.

The gate is git-agnostic: CI extracts the merge-base copies (git show) and passes
file paths; a missing base spec means "nothing to gate" (new file). Usage:

    python tests/contract/check_version_bump.py \
        --base-spec /tmp/base-openapi.yml   --head-spec api/openapi.yml \
        --base-changelog /tmp/base-CHANGELOG.md --head-changelog api/CHANGELOG.md

Exit code 0 = pass, 1 = gate violation (findings printed), 2 = usage error.
Dependencies: PyYAML only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

GOVERNANCE_DOC = "doc/governance/api-contract-governance.md"


def parse_semver(version: str) -> tuple[int, int, int] | None:
    parts = str(version).split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    major, minor, patch = (int(p) for p in parts)
    return (major, minor, patch)


def spec_version(spec_text: str) -> str | None:
    try:
        doc = yaml.safe_load(spec_text)
    except yaml.YAMLError:
        return None
    if not isinstance(doc, dict):
        return None
    info = doc.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    return None if version is None else str(version)


def changelog_has_entry(changelog_text: str, version: str) -> bool:
    return any(line.strip().startswith(f"## {version}") for line in changelog_text.splitlines())


def evaluate(
    base_spec: str | None,
    head_spec: str,
    base_changelog: str,
    head_changelog: str,
) -> list[str]:
    """Return gate violations (empty list == pass). Pure function — no I/O."""
    if base_spec is None:
        return []  # spec did not exist at the merge base — nothing to gate
    if base_spec == head_spec:
        return []  # spec unchanged — version/CHANGELOG requirements do not apply

    findings: list[str] = []
    base_version, head_version = spec_version(base_spec), spec_version(head_spec)
    base_sv = parse_semver(base_version) if base_version else None
    head_sv = parse_semver(head_version) if head_version else None

    if head_sv is None:
        findings.append(
            f"head api/openapi.yml info.version '{head_version}' is not semver "
            f"MAJOR.MINOR.PATCH ({GOVERNANCE_DOC} §2)")
    elif base_sv is not None and head_sv <= base_sv:
        findings.append(
            f"api/openapi.yml changed but info.version was not bumped "
            f"(base={base_version}, head={head_version}) — bump per {GOVERNANCE_DOC} §2 "
            "(MAJOR=breaking, MINOR=additive, PATCH=doc-only)")

    if head_changelog == base_changelog:
        findings.append(
            f"api/openapi.yml changed but api/CHANGELOG.md was not updated "
            f"({GOVERNANCE_DOC} §6: one entry per API change)")
    elif head_sv is not None and not changelog_has_entry(head_changelog, str(head_version)):
        findings.append(
            f"api/CHANGELOG.md has no '## {head_version}' entry for the new spec version "
            f"({GOVERNANCE_DOC} §6)")
    return findings


def _read_optional(path: str) -> str | None:
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.is_file() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-spec", required=True,
                        help="merge-base api/openapi.yml (may not exist → gate skipped)")
    parser.add_argument("--head-spec", required=True, help="current api/openapi.yml")
    parser.add_argument("--base-changelog", required=True,
                        help="merge-base api/CHANGELOG.md (may not exist → treated as empty)")
    parser.add_argument("--head-changelog", required=True,
                        help="current api/CHANGELOG.md (may not exist → treated as empty)")
    args = parser.parse_args(argv)

    head_spec = _read_optional(args.head_spec)
    if head_spec is None:
        print(f"ERROR: head spec not found: {args.head_spec}", file=sys.stderr)
        return 2

    findings = evaluate(
        base_spec=_read_optional(args.base_spec),
        head_spec=head_spec,
        base_changelog=_read_optional(args.base_changelog) or "",
        head_changelog=_read_optional(args.head_changelog) or "",
    )
    if findings:
        print("API version-bump gate FAILED:")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("API version-bump gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
