"""Unit tests for the version-bump gate (check_version_bump.evaluate + CLI).

Pure text inputs — no git, no Docker. The gate's rules come from
doc/governance/api-contract-governance.md §2 (semver bump) and §6 (CHANGELOG).
"""
from __future__ import annotations

import pytest

from .check_version_bump import changelog_has_entry, evaluate, main, parse_semver, spec_version

SPEC_130 = "openapi: 3.1.0\ninfo:\n  title: EMS API\n  version: 1.3.0\npaths: {}\n"
SPEC_130_CHANGED = SPEC_130.replace("paths: {}", "paths: {/new: {}}")
SPEC_140 = SPEC_130_CHANGED.replace("version: 1.3.0", "version: 1.4.0")
SPEC_120 = SPEC_130_CHANGED.replace("version: 1.3.0", "version: 1.2.0")
CHANGELOG_130 = "# API CHANGELOG\n\n## 1.3.0 — 2026-06-10（MINOR）\n- stuff\n"
CHANGELOG_140 = "# API CHANGELOG\n\n## 1.4.0 — 2026-06-11（MINOR）\n- new\n" + CHANGELOG_130


def test_unchanged_spec_passes_without_version_bump():
    findings = evaluate(SPEC_130, SPEC_130, CHANGELOG_130, CHANGELOG_130)
    assert findings == [], f"unchanged spec must pass, got: {findings}"


def test_missing_base_spec_skips_gate():
    findings = evaluate(None, SPEC_130, "", CHANGELOG_130)
    assert findings == [], f"new spec file (no base) must pass, got: {findings}"


def test_changed_spec_with_bump_and_changelog_entry_passes():
    findings = evaluate(SPEC_130, SPEC_140, CHANGELOG_130, CHANGELOG_140)
    assert findings == [], f"properly governed change must pass, got: {findings}"


def test_changed_spec_without_version_bump_fails():
    findings = evaluate(SPEC_130, SPEC_130_CHANGED, CHANGELOG_130, CHANGELOG_140)
    assert any("not bumped" in f for f in findings), f"expected version-bump finding, got: {findings}"


def test_changed_spec_with_version_downgrade_fails():
    findings = evaluate(SPEC_130, SPEC_120, CHANGELOG_130, CHANGELOG_140)
    assert any("not bumped" in f for f in findings), f"expected downgrade finding, got: {findings}"


def test_changed_spec_without_changelog_update_fails():
    findings = evaluate(SPEC_130, SPEC_140, CHANGELOG_130, CHANGELOG_130)
    assert any("CHANGELOG.md was not updated" in f for f in findings), (
        f"expected stale-CHANGELOG finding, got: {findings}")


def test_changed_spec_with_changelog_lacking_version_entry_fails():
    changelog_no_entry = CHANGELOG_130 + "\nsome unrelated edit\n"
    findings = evaluate(SPEC_130, SPEC_140, CHANGELOG_130, changelog_no_entry)
    assert any("no '## 1.4.0' entry" in f for f in findings), (
        f"expected missing-entry finding, got: {findings}")


def test_non_semver_head_version_fails():
    bad = SPEC_130_CHANGED.replace("version: 1.3.0", "version: v2-beta")
    findings = evaluate(SPEC_130, bad, CHANGELOG_130, CHANGELOG_140)
    assert any("not semver" in f for f in findings), f"expected semver finding, got: {findings}"


@pytest.mark.parametrize(
    ("version", "expected"),
    [("1.3.0", (1, 3, 0)), ("10.0.2", (10, 0, 2)), ("1.3", None), ("1.3.0-rc1", None), ("x.y.z", None)],
)
def test_parse_semver_accepts_only_major_minor_patch(version, expected):
    assert parse_semver(version) == expected, f"parse_semver({version!r}) != {expected}"


def test_spec_version_reads_info_version_not_openapi_field():
    assert spec_version(SPEC_130) == "1.3.0", "must read info.version (1.3.0), not openapi: 3.1.0"
    assert spec_version("not: [valid") is None, "unparseable yaml must yield None, not raise"


def test_changelog_entry_match_allows_suffix_after_version():
    assert changelog_has_entry(CHANGELOG_130, "1.3.0"), "## 1.3.0 — ...（MINOR）must match"
    assert not changelog_has_entry(CHANGELOG_130, "1.4.0"), "absent version must not match"


def test_cli_exits_nonzero_on_violation_and_zero_on_pass(tmp_path, capsys):
    base_spec = tmp_path / "base.yml"
    head_spec = tmp_path / "head.yml"
    base_log = tmp_path / "base-log.md"
    head_log = tmp_path / "head-log.md"
    base_spec.write_text(SPEC_130, encoding="utf-8")
    head_spec.write_text(SPEC_130_CHANGED, encoding="utf-8")  # changed, no bump
    base_log.write_text(CHANGELOG_130, encoding="utf-8")
    head_log.write_text(CHANGELOG_130, encoding="utf-8")
    args = ["--base-spec", str(base_spec), "--head-spec", str(head_spec),
            "--base-changelog", str(base_log), "--head-changelog", str(head_log)]

    rc_fail = main(args)
    assert rc_fail == 1, f"violation must exit 1, got {rc_fail}: {capsys.readouterr().out}"

    head_spec.write_text(SPEC_140, encoding="utf-8")
    head_log.write_text(CHANGELOG_140, encoding="utf-8")
    rc_pass = main(args)
    assert rc_pass == 0, f"governed change must exit 0, got {rc_pass}: {capsys.readouterr().out}"


def test_cli_missing_base_files_is_tolerated(tmp_path):
    head_spec = tmp_path / "head.yml"
    head_log = tmp_path / "head-log.md"
    head_spec.write_text(SPEC_130, encoding="utf-8")
    head_log.write_text(CHANGELOG_130, encoding="utf-8")
    rc = main(["--base-spec", str(tmp_path / "absent.yml"), "--head-spec", str(head_spec),
               "--base-changelog", str(tmp_path / "absent.md"), "--head-changelog", str(head_log)])
    assert rc == 0, f"missing merge-base files must skip the gate (exit 0), got {rc}"
