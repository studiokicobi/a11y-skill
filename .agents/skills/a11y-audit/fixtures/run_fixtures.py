#!/usr/bin/env python3
"""
run_fixtures.py — regression test runner for static and triage fixtures.

Scans each fixture directory and compares the output against that fixture's
snapshot files. Prints a pass/fail summary and exits non-zero on any failure.
Meant to be run from the skill root:

    python3 fixtures/run_fixtures.py

To update snapshots after an intentional scanner change:

    python3 fixtures/run_fixtures.py --update
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).parent.parent
FIXTURES_ROOT = Path(__file__).parent
SCANNER = SKILL_ROOT / "scripts" / "a11y_scan.py"
TRIAGE = SKILL_ROOT / "scripts" / "triage.py"
FIXED_DETECTED_AT = "2026-01-02T03:04:05Z"


def normalize(scan_output: dict, fixture_name: str) -> dict:
    """Strip absolute paths so snapshots are portable across machines."""
    fixture_root = f"fixtures/{fixture_name}"
    out = {
        "framework": scan_output["framework"],
        "files_scanned": scan_output["files_scanned"],
        "issue_count": scan_output["issue_count"],
        "issues": [],
    }
    for issue in scan_output["issues"]:
        parts = issue["file"].split(f"{fixture_name}/")
        rel_file = (fixture_root + "/" + parts[-1]) if len(parts) > 1 else issue["file"]
        out["issues"].append({
            "rule_id": issue["rule_id"],
            "wcag": issue["wcag"],
            "file": rel_file,
            "line": issue["line"],
            "triage_hint": issue["triage_hint"],
        })
    # Stable sort for diff friendliness
    out["issues"].sort(key=lambda x: (x["file"], x["line"], x["rule_id"]))
    return out


def normalize_report(report: str) -> str:
    normalized = re.sub(r"(\*\*Date\*\*: )\d{4}-\d{2}-\d{2}", r"\1<DATE>", report)
    return normalized.rstrip()


def normalize_report_json(report: dict) -> dict:
    """Keep comparisons deterministic and compact across environments."""
    normalized = {
        "schema_version": report["schema_version"],
        "generated_at": report["generated_at"],
        "target": report["target"],
        "framework": report["framework"],
        "standard": report["standard"],
        "summary": report["summary"],
        "coverage_metadata": report["coverage_metadata"],
        "findings": [],
        "not_checked": [],
    }

    for finding in report["findings"]:
        if finding["triage_group"] == "not_checked":
            normalized["not_checked"].append({
                "rule_id": finding["rule_id"],
                "title": finding["title"],
                "wcag": finding["wcag"],
                "status": finding["status"],
                "notes": finding["proposed_fix"]["notes"],
            })
            continue

        compact = {
            "id": finding["id"],
            "rule_id": finding["rule_id"],
            "title": finding["title"],
            "wcag": finding["wcag"],
            "severity": finding["severity"],
            "scanner": finding["scanner"],
            "scanner_version": finding["scanner_version"],
            "detected_at": finding["detected_at"],
            "triage_group": finding["triage_group"],
            "fix_safety": finding["fix_safety"],
            "confidence": finding["confidence"],
            "status": finding["status"],
            "group_reason": finding["group_reason"],
            "location": finding["location"],
            "evidence": finding["evidence"],
            "decision_required": finding["decision_required"],
            "proposed_fix": finding["proposed_fix"],
            "fingerprint": finding["fingerprint"],
            "confirmed_by": finding["confirmed_by"],
            "waiver": finding["waiver"],
        }
        if "origin_rule_id" in finding:
            compact["origin_rule_id"] = finding["origin_rule_id"]
        normalized["findings"].append(compact)

    return normalized


def run_static_fixture(fixture_dir: Path, update: bool = False) -> bool:
    """Returns True if the static fixture passes (or was updated), False on failure."""
    name = fixture_dir.name
    expected_path = fixture_dir / "expected.json"

    result = subprocess.run(
        [sys.executable, str(SCANNER), str(fixture_dir), "--quiet", "--output", "/tmp/actual.json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  FAIL {name}: scanner exited {result.returncode}")
        print(f"        stderr: {result.stderr.strip()}")
        return False

    actual = normalize(json.loads(Path("/tmp/actual.json").read_text()), name)

    if update:
        expected_path.write_text(json.dumps(actual, indent=2))
        print(f"  UPDATED {name}: {actual['issue_count']} issues, framework={actual['framework']}")
        return True

    if not expected_path.exists():
        print(f"  FAIL {name}: no expected.json found (run with --update to create)")
        return False

    expected = json.loads(expected_path.read_text())

    if actual == expected:
        print(f"  PASS {name}: {actual['issue_count']} issues, framework={actual['framework']}")
        return True

    # Detailed failure
    print(f"  FAIL {name}:")
    if actual["framework"] != expected["framework"]:
        print(f"        framework: expected {expected['framework']!r}, got {actual['framework']!r}")
    if actual["issue_count"] != expected["issue_count"]:
        print(f"        issue count: expected {expected['issue_count']}, got {actual['issue_count']}")

    # Diff the issues
    expected_keys = {(i["rule_id"], i["file"], i["line"]) for i in expected["issues"]}
    actual_keys = {(i["rule_id"], i["file"], i["line"]) for i in actual["issues"]}
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    for k in missing:
        print(f"        missing:  {k[0]} at {k[1]}:{k[2]}")
    for k in extra:
        print(f"        extra:    {k[0]} at {k[1]}:{k[2]}")
    return False


def run_triage_fixture(fixture_dir: Path, update: bool = False) -> bool:
    """Returns True if the triage fixture passes (or was updated), False on failure."""
    name = fixture_dir.name
    expected_markdown_path = fixture_dir / "expected.md"
    expected_json_path = fixture_dir / "expected.report.json"
    runtime_path = fixture_dir / "runtime.json"
    static_path = fixture_dir / "static.json"
    status_path = fixture_dir / "status.json"
    output_markdown_path = Path("/tmp/triage-report.md")
    output_json_path = Path("/tmp/triage-report.json")

    cmd = [
        sys.executable,
        str(TRIAGE),
        "--output",
        str(output_markdown_path),
        "--json-output",
        str(output_json_path),
        "--detected-at",
        FIXED_DETECTED_AT,
    ]
    if static_path.exists():
        cmd.extend(["--static", str(static_path)])
    if runtime_path.exists():
        cmd.extend(["--runtime", str(runtime_path)])
    if status_path.exists():
        cmd.extend(["--status-file", str(status_path)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAIL {name}: triage exited {result.returncode}")
        print(f"        stderr: {result.stderr.strip()}")
        return False

    actual_markdown = normalize_report(output_markdown_path.read_text())
    actual_json = normalize_report_json(json.loads(output_json_path.read_text()))

    if update:
        expected_markdown_path.write_text(actual_markdown)
        expected_json_path.write_text(json.dumps(actual_json, indent=2) + "\n")
        print(f"  UPDATED {name}: triage snapshots refreshed")
        return True

    if not expected_markdown_path.exists() and not expected_json_path.exists():
        print(f"  FAIL {name}: no expected.md or expected.report.json found (run with --update to create)")
        return False

    ok = True
    if expected_markdown_path.exists():
        expected_markdown = normalize_report(expected_markdown_path.read_text())
        if actual_markdown == expected_markdown:
            print(f"  PASS {name}: triage markdown matched snapshot")
        else:
            print(f"  FAIL {name}: triage markdown differed from expected.md")
            ok = False

    if expected_json_path.exists():
        expected_json = json.loads(expected_json_path.read_text())
        if actual_json == expected_json:
            print(f"  PASS {name}: triage JSON matched snapshot")
        else:
            print(f"  FAIL {name}: triage JSON differed from expected.report.json")
            ok = False

    return ok


def run_fixture(fixture_dir: Path, update: bool = False) -> bool:
    """Returns True if the fixture passes (or was updated), False on failure."""
    if (fixture_dir / "runtime.json").exists() or (fixture_dir / "static.json").exists():
        return run_triage_fixture(fixture_dir, update=update)
    return run_static_fixture(fixture_dir, update=update)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true",
                        help="Regenerate expected.json snapshots instead of comparing")
    parser.add_argument("--only", type=str, default=None,
                        help="Run only the named fixture")
    args = parser.parse_args()

    fixtures = sorted(
        d for d in FIXTURES_ROOT.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (
            args.update
            or (d / "expected.json").exists()
            or (d / "expected.md").exists()
            or (d / "expected.report.json").exists()
        )
    )
    if args.only:
        fixtures = [d for d in FIXTURES_ROOT.iterdir() if d.is_dir() and d.name == args.only]

    if not fixtures:
        print("No fixtures found.")
        return 2

    action = "Updating" if args.update else "Running"
    print(f"{action} {len(fixtures)} fixture(s):")

    passed = 0
    failed = 0
    for fixture_dir in fixtures:
        ok = run_fixture(fixture_dir, update=args.update)
        if ok:
            passed += 1
        else:
            failed += 1

    print()
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
