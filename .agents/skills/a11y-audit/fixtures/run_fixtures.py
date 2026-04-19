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
CLI = SKILL_ROOT / "scripts" / "cli.py"
RUNTIME = SKILL_ROOT / "scripts" / "a11y_runtime.js"
STATEFUL = SKILL_ROOT / "scripts" / "a11y_stateful.js"
TOKENS = SKILL_ROOT / "scripts" / "tokens.py"
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
        "baseline_comparison": report.get("baseline_comparison", {}),
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
            "mapping": finding["mapping"],
            "evidence": finding["evidence"],
            "decision_required": finding["decision_required"],
            "proposed_fix": finding["proposed_fix"],
            "fingerprint": finding["fingerprint"],
            "confirmed_by": finding["confirmed_by"],
            "waiver": finding["waiver"],
        }
        if "comparison" in finding:
            compact["comparison"] = finding["comparison"]
        if "fingerprint_data" in finding:
            compact["fingerprint_data"] = finding["fingerprint_data"]
        if "blast_radius" in finding:
            compact["blast_radius"] = finding["blast_radius"]
        if "origin_rule_id" in finding:
            compact["origin_rule_id"] = finding["origin_rule_id"]
        normalized["findings"].append(compact)

    return normalized


def normalize_runtime_output(runtime_output: dict, fixture_name: str) -> dict:
    fixture_url = Path(FIXTURES_ROOT / fixture_name / "index.html").resolve().as_uri()

    def normalize_url(value: str) -> str:
        if value == fixture_url:
            return f"file://fixtures/{fixture_name}/index.html"
        return value

    def normalize_screenshot(value: str) -> str:
        if not value:
            return ""
        screenshot_path = Path(value)
        if not screenshot_path.is_absolute():
            return value
        parent = screenshot_path.parent.name
        if parent:
            return f"{parent}/{screenshot_path.name}"
        return screenshot_path.name

    out = {
        "scanner": runtime_output["scanner"],
        "engine": runtime_output.get("engine", ""),
        "browser": runtime_output.get("browser", ""),
        "issue_count": runtime_output["issue_count"],
        "has_passes": runtime_output.get("pass_count", 0) > 0,
        "issues": [],
    }
    for issue in runtime_output.get("issues", []):
        out["issues"].append({
            "rule_id": issue["rule_id"],
            "origin_rule_id": issue.get("origin_rule_id", ""),
            "wcag": issue["wcag"],
            "file": normalize_url(issue["file"]),
            "triage_hint": issue["triage_hint"],
            "result_type": issue.get("fix_data", {}).get("result_type", ""),
            "target": issue.get("fix_data", {}).get("target", ""),
            "screenshot": normalize_screenshot(issue.get("fix_data", {}).get("screenshot", "")),
        })
    out["issues"].sort(key=lambda item: (item["rule_id"], item["file"], item["target"]))
    return out


def normalize_stateful_output(stateful_output: dict, fixture_name: str) -> dict:
    fixture_root = FIXTURES_ROOT / fixture_name

    def normalize_url(value: str) -> str:
        if not value:
            return ""
        if not value.startswith("file://"):
            return value
        base_value, hash_sep, fragment = value.partition("#")
        for candidate in fixture_root.rglob("*"):
            if candidate.is_file() and candidate.resolve().as_uri() == base_value:
                relative = candidate.relative_to(fixture_root).as_posix()
                normalized = f"file://fixtures/{fixture_name}/{relative}"
                return f"{normalized}#{fragment}" if hash_sep else normalized
        return value

    def normalize_screenshot(value: str) -> str:
        if not value:
            return ""
        screenshot_path = Path(value)
        if not screenshot_path.is_absolute():
            return value
        parent = screenshot_path.parent.name
        return f"{parent}/{screenshot_path.name}" if parent else screenshot_path.name

    out = {
        "scanner": stateful_output["scanner"],
        "engine": stateful_output.get("engine", ""),
        "browser": stateful_output.get("browser", ""),
        "issue_count": stateful_output["issue_count"],
        "checkpoint_count": len(stateful_output.get("checkpoints", [])),
        "step_failure_count": len(stateful_output.get("step_failures", [])),
        "issues": [],
        "checkpoints": [],
        "focus_transitions": [],
    }
    for issue in stateful_output.get("issues", []):
        out["issues"].append({
            "rule_id": issue["rule_id"],
            "origin_rule_id": issue.get("origin_rule_id", ""),
            "wcag": issue["wcag"],
            "file": normalize_url(issue["file"]),
            "journey_step_id": issue.get("journey_step_id", ""),
            "triage_hint": issue["triage_hint"],
            "result_type": issue.get("fix_data", {}).get("result_type", ""),
            "target": issue.get("fix_data", {}).get("target", ""),
            "screenshot": normalize_screenshot(issue.get("fix_data", {}).get("screenshot", "")),
        })
    for checkpoint in stateful_output.get("checkpoints", []):
        out["checkpoints"].append({
            "journey_id": checkpoint.get("journey_id", ""),
            "journey_step_id": checkpoint.get("journey_step_id", ""),
            "url": normalize_url(checkpoint.get("url", "")),
            "issue_count": checkpoint.get("counts", {}).get("issues", 0),
            "screenshot": normalize_screenshot(checkpoint.get("screenshot", "")),
        })
    for transition in stateful_output.get("focus_transitions", []):
        out["focus_transitions"].append({
            "journey_step_id": transition.get("journey_step_id", ""),
            "action": transition.get("action", ""),
            "before_url": normalize_url(transition.get("before_url", "")),
            "url": normalize_url(transition.get("url", "")),
            "before": transition.get("before", ""),
            "after": transition.get("after", ""),
        })
    out["issues"].sort(key=lambda item: (item["journey_step_id"], item["rule_id"], item["target"]))
    out["checkpoints"].sort(key=lambda item: (item["journey_step_id"], item["url"]))
    out["focus_transitions"].sort(key=lambda item: (item["journey_step_id"], item["action"]))
    return out


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


def run_runtime_smoke_fixture(fixture_dir: Path, update: bool = False) -> bool:
    name = fixture_dir.name
    expected_path = fixture_dir / "expected.runtime.json"
    output_path = Path("/tmp/runtime-actual.json")
    screenshot_dir = Path("/tmp/runtime-screenshots")
    html_path = fixture_dir / "index.html"
    config_path = fixture_dir / "runtime.config.json"

    cmd = [
        "node",
        str(RUNTIME),
        "--url",
        html_path.resolve().as_uri(),
        "--output",
        str(output_path),
    ]
    if config_path.exists():
        cmd.extend(["--config", str(config_path)])
    if screenshot_dir:
        cmd.extend(["--screenshot-dir", str(screenshot_dir)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAIL {name}: runtime scan exited {result.returncode}")
        print(f"        stderr: {result.stderr.strip()}")
        return False

    actual = normalize_runtime_output(json.loads(output_path.read_text()), name)

    if update:
        expected_path.write_text(json.dumps(actual, indent=2) + "\n")
        print(f"  UPDATED {name}: runtime snapshot refreshed")
        return True

    if not expected_path.exists():
        print(f"  FAIL {name}: no expected.runtime.json found (run with --update to create)")
        return False

    expected = json.loads(expected_path.read_text())
    if actual == expected:
        print(f"  PASS {name}: runtime scan matched snapshot")
        return True

    print(f"  FAIL {name}: runtime scan differed from expected.runtime.json")
    return False


def run_stateful_smoke_fixture(fixture_dir: Path, update: bool = False) -> bool:
    name = fixture_dir.name
    expected_path = fixture_dir / "expected.stateful.json"
    output_path = Path("/tmp/stateful-actual.json")
    screenshot_dir = Path("/tmp/stateful-screenshots")
    config_path = fixture_dir / "journey.config.json"

    cmd = [
        "node",
        str(STATEFUL),
        "--config",
        str(config_path),
        "--output",
        str(output_path),
    ]
    if screenshot_dir:
        cmd.extend(["--screenshot-dir", str(screenshot_dir)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAIL {name}: stateful scan exited {result.returncode}")
        print(f"        stderr: {result.stderr.strip()}")
        return False

    actual = normalize_stateful_output(json.loads(output_path.read_text()), name)

    if update:
        expected_path.write_text(json.dumps(actual, indent=2) + "\n")
        print(f"  UPDATED {name}: stateful snapshot refreshed")
        return True

    if not expected_path.exists():
        print(f"  FAIL {name}: no expected.stateful.json found (run with --update to create)")
        return False

    expected = json.loads(expected_path.read_text())
    if actual == expected:
        print(f"  PASS {name}: stateful scan matched snapshot")
        return True

    print(f"  FAIL {name}: stateful scan differed from expected.stateful.json")
    return False


def run_runtime_error_fixture(fixture_dir: Path) -> bool:
    name = fixture_dir.name
    expected_path = fixture_dir / "expected.error.txt"
    config_path = fixture_dir / "runtime.config.json"

    cmd = [
        "node",
        str(RUNTIME),
        "--url",
        "http://localhost.invalid",
        "--config",
        str(config_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr.strip()

    if result.returncode == 0:
        print(f"  FAIL {name}: expected runtime command to fail")
        return False
    if not expected_path.exists():
        print(f"  FAIL {name}: no expected.error.txt found")
        return False

    expected = expected_path.read_text().strip()
    if stderr == expected:
        print(f"  PASS {name}: runtime error matched expected redacted message")
        return True

    print(f"  FAIL {name}: runtime error differed from expected.error.txt")
    return False


def run_triage_fixture(fixture_dir: Path, update: bool = False) -> bool:
    """Returns True if the triage fixture passes (or was updated), False on failure."""
    name = fixture_dir.name
    expected_markdown_path = fixture_dir / "expected.md"
    expected_json_path = fixture_dir / "expected.report.json"
    runtime_path = fixture_dir / "runtime.json"
    stateful_path = fixture_dir / "stateful.json"
    static_path = fixture_dir / "static.json"
    tokens_path = fixture_dir / "tokens.json"
    baseline_path = fixture_dir / "baseline.json"
    status_path = fixture_dir / "status.json"
    tokens_output_path = Path("/tmp/tokens-report.json")
    output_markdown_path = Path("/tmp/triage-report.md")
    output_json_path = Path("/tmp/triage-report.json")
    for path in (tokens_output_path, output_markdown_path, output_json_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

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
    if stateful_path.exists():
        cmd.extend(["--stateful", str(stateful_path)])
    if tokens_path.exists():
        token_result = subprocess.run(
            [sys.executable, str(TOKENS), str(tokens_path), "--output", str(tokens_output_path)],
            capture_output=True, text=True,
        )
        if token_result.returncode != 0:
            print(f"  FAIL {name}: token scan exited {token_result.returncode}")
            print(f"        stderr: {token_result.stderr.strip()}")
            return False
        cmd.extend(["--tokens", str(tokens_output_path)])
    if baseline_path.exists():
        cmd.extend(["--baseline-file", str(baseline_path)])
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


def run_cli_fixture(fixture_dir: Path, update: bool = False) -> bool:
    name = fixture_dir.name
    expected_summary_path = fixture_dir / "expected.summary.md"
    expected_exit_path = fixture_dir / "expected.exit.txt"
    expected_json_path = fixture_dir / "expected.report.json"
    runtime_path = fixture_dir / "runtime.json"
    stateful_path = fixture_dir / "stateful.json"
    static_path = fixture_dir / "static.json"
    tokens_path = fixture_dir / "tokens.json"
    baseline_path = fixture_dir / "baseline.json"
    status_path = fixture_dir / "status.json"
    changed_files_path = fixture_dir / "changed-files.txt"
    token_output_path = Path("/tmp/cli-tokens.json")
    summary_output_path = Path("/tmp/pr-summary.md")
    output_json_path = Path("/tmp/cli-report.json")
    for path in (token_output_path, summary_output_path, output_json_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    cmd = [
        sys.executable,
        str(CLI),
        "--json-output",
        str(output_json_path),
        "--pr-summary-output",
        str(summary_output_path),
        "--detected-at",
        FIXED_DETECTED_AT,
        "--ci",
    ]
    if static_path.exists():
        cmd.extend(["--static", str(static_path)])
    if runtime_path.exists():
        cmd.extend(["--runtime", str(runtime_path)])
    if stateful_path.exists():
        cmd.extend(["--stateful", str(stateful_path)])
    if tokens_path.exists():
        token_result = subprocess.run(
            [sys.executable, str(TOKENS), str(tokens_path), "--output", str(token_output_path)],
            capture_output=True, text=True,
        )
        if token_result.returncode != 0:
            print(f"  FAIL {name}: token scan exited {token_result.returncode}")
            print(f"        stderr: {token_result.stderr.strip()}")
            return False
        cmd.extend(["--tokens", str(token_output_path)])
    if baseline_path.exists():
        cmd.extend(["--baseline-file", str(baseline_path)])
    if status_path.exists():
        cmd.extend(["--status-file", str(status_path)])
    if changed_files_path.exists():
        cmd.extend(["--changed-files", str(changed_files_path)])

    result = subprocess.run(cmd, capture_output=True, text=True)
    actual_exit = result.returncode
    actual_summary = normalize_report(summary_output_path.read_text()) if summary_output_path.exists() else ""
    actual_json = json.loads(output_json_path.read_text()) if output_json_path.exists() else None

    if update:
        if expected_summary_path or actual_summary:
            expected_summary_path.write_text(actual_summary)
        if actual_json is not None:
            expected_json_path.write_text(json.dumps(normalize_report_json(actual_json), indent=2) + "\n")
        expected_exit_path.write_text(str(actual_exit) + "\n")
        print(f"  UPDATED {name}: CLI snapshots refreshed")
        return True

    ok = True
    if expected_exit_path.exists():
        expected_exit = int(expected_exit_path.read_text().strip())
        if actual_exit == expected_exit:
            print(f"  PASS {name}: CLI exit code matched snapshot")
        else:
            print(f"  FAIL {name}: CLI exit code expected {expected_exit}, got {actual_exit}")
            ok = False

    if expected_summary_path.exists():
        expected_summary = normalize_report(expected_summary_path.read_text())
        if actual_summary == expected_summary:
            print(f"  PASS {name}: PR summary matched snapshot")
        else:
            print(f"  FAIL {name}: PR summary differed from expected.summary.md")
            ok = False

    if expected_json_path.exists():
        if actual_json is None:
            print(f"  FAIL {name}: CLI did not write expected.report.json output")
            ok = False
        else:
            expected_json = json.loads(expected_json_path.read_text())
            normalized_actual_json = normalize_report_json(actual_json)
            if normalized_actual_json == expected_json:
                print(f"  PASS {name}: CLI JSON matched snapshot")
            else:
                print(f"  FAIL {name}: CLI JSON differed from expected.report.json")
                ok = False

    return ok


def run_fixture(fixture_dir: Path, update: bool = False) -> bool:
    """Returns True if the fixture passes (or was updated), False on failure."""
    if (fixture_dir / "cli.fixture").exists() or (fixture_dir / "expected.summary.md").exists() or (fixture_dir / "expected.exit.txt").exists():
        return run_cli_fixture(fixture_dir, update=update)
    if (fixture_dir / "expected.stateful.json").exists():
        return run_stateful_smoke_fixture(fixture_dir, update=update)
    if (fixture_dir / "expected.runtime.json").exists():
        return run_runtime_smoke_fixture(fixture_dir, update=update)
    if (fixture_dir / "expected.error.txt").exists():
        return run_runtime_error_fixture(fixture_dir)
    if (
        (fixture_dir / "runtime.json").exists()
        or (fixture_dir / "static.json").exists()
        or (fixture_dir / "stateful.json").exists()
        or (fixture_dir / "tokens.json").exists()
    ):
        return run_triage_fixture(fixture_dir, update=update)
    return run_static_fixture(fixture_dir, update=update)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true",
                        help="Regenerate expected.json snapshots instead of comparing")
    parser.add_argument("--only", type=str, default=None,
                        help="Run only the named fixture")
    parser.add_argument("--live-runtime", action="store_true",
                        help="Include live Playwright browser fixtures")
    args = parser.parse_args()

    fixtures = sorted(
        d for d in FIXTURES_ROOT.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (
            args.update
            or (d / "expected.json").exists()
            or (d / "expected.md").exists()
            or (d / "expected.report.json").exists()
            or (d / "expected.summary.md").exists()
            or (d / "expected.exit.txt").exists()
            or (d / "expected.error.txt").exists()
            or (args.live_runtime and ((d / "expected.runtime.json").exists() or (d / "expected.stateful.json").exists()))
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
