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
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional


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


def _fixture_text_root(fixture_name: str) -> str:
    return f"fixtures/{fixture_name}"


def normalize_fixture_value(value, fixture_name: str, path_aliases: Optional[Dict[str, str]] = None):
    fixture_dir = (FIXTURES_ROOT / fixture_name).resolve()
    fixture_root = _fixture_text_root(fixture_name)
    fixture_uri = fixture_dir.as_uri()
    path_aliases = path_aliases or {}

    if isinstance(value, str):
        normalized = value.replace(str(fixture_dir), fixture_root)
        normalized = normalized.replace(str(fixture_dir).replace("\\", "/"), fixture_root)
        if value.startswith(fixture_uri):
            normalized = normalized.replace(fixture_uri, f"file://{fixture_root}")
        for source, target in sorted(path_aliases.items(), key=lambda item: len(item[0]), reverse=True):
            normalized = normalized.replace(source, target)
            normalized = normalized.replace(source.replace("\\", "/"), target)
        return normalized
    if isinstance(value, list):
        return [normalize_fixture_value(item, fixture_name, path_aliases=path_aliases) for item in value]
    if isinstance(value, dict):
        return {
            key: normalize_fixture_value(item, fixture_name, path_aliases=path_aliases)
            for key, item in value.items()
        }
    return value


def _audit_output_aliases(fixture_name: str, output_dir: Path) -> Dict[str, str]:
    alias_root = f"artifacts/{fixture_name}-audit-output"
    aliases = {
        str(output_dir): alias_root,
        str(output_dir.resolve()): alias_root,
    }
    aliases[output_dir.as_uri()] = f"file://{alias_root}"
    aliases[output_dir.resolve().as_uri()] = f"file://{alias_root}"
    return aliases


def normalize_report_json(report: dict, fixture_name: Optional[str] = None) -> dict:
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

    if fixture_name:
        normalized = normalize_fixture_value(normalized, fixture_name)
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
        capture_output=True, text=True, cwd=str(SKILL_ROOT),
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

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
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

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
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
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
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


def run_cli_error_fixture(fixture_dir: Path, update: bool = False) -> bool:
    """CLI invocations that MUST fail — validates exit code and stderr.

    Fixture layout:
        cli-error.fixture.json           { "args": ["ci", "--runtime", "./runtime.json"] }
        expected.exit.txt                exit code (usually 2)
        expected.stderr.starts_with.txt  prefix that stderr's first non-empty
                                         line MUST start with (strong guard —
                                         catches tracebacks / wrong wrappers)
        expected.stderr.contains.txt     (optional) additional substring that
                                         must appear anywhere in stderr
        <any referenced files>           e.g. runtime.json with a malformed payload

    The `starts_with` file is the strong regression guard Codex round-2 #6
    asked for: a Python traceback that happens to contain the expected
    phrase deeper in its output would fail because its first non-empty
    line is "Traceback (most recent call last):", not the clean
    `Configuration error:` wrapper. At least one of `starts_with` or
    `contains` must be present.

    We don't snapshot the whole first line because it can include a
    fully-resolved absolute path (not portable across machines). A prefix
    snapshot captures the clean-wrapper invariant without embedding
    machine-specific content.

    Args use `./<path>` to refer to a file in the fixture directory — resolved
    to an absolute path at run time so the CLI sees a real file.
    """
    name = fixture_dir.name
    spec_path = fixture_dir / "cli-error.fixture.json"
    expected_exit_path = fixture_dir / "expected.exit.txt"
    expected_starts_with_path = fixture_dir / "expected.stderr.starts_with.txt"
    expected_contains_path = fixture_dir / "expected.stderr.contains.txt"

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    raw_args = spec.get("args", [])
    resolved_args: list = []
    for arg in raw_args:
        if isinstance(arg, str) and arg.startswith("./"):
            resolved_args.append(str((fixture_dir / arg[2:]).resolve()))
        else:
            resolved_args.append(arg)

    output_dir = Path(f"/tmp/cli-error-fixture-{name}")
    if output_dir.exists():
        shutil.rmtree(output_dir)

    cmd = [sys.executable, str(CLI), *resolved_args]
    if "--output-dir" not in raw_args:
        cmd.extend(["--output-dir", str(output_dir)])
    if "--detected-at" not in raw_args:
        cmd.extend(["--detected-at", FIXED_DETECTED_AT])

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
    actual_exit = result.returncode
    actual_stderr = result.stderr
    # Skip leading blank lines so a traceback's empty preamble can't hide the
    # real first line.
    stderr_lines = [line for line in actual_stderr.splitlines() if line.strip()]
    actual_first_line = stderr_lines[0] if stderr_lines else ""

    if update:
        expected_exit_path.write_text(str(actual_exit) + "\n", encoding="utf-8")
        # Default to the clean-wrapper prefix as the strong guard. Callers who
        # want a longer or looser starts-with can edit the file after update.
        if not expected_starts_with_path.exists():
            expected_starts_with_path.write_text("Configuration error: \n", encoding="utf-8")
        print(f"  UPDATED {name}: CLI error snapshot refreshed")
        return True

    ok = True
    if expected_exit_path.exists():
        expected_exit = int(expected_exit_path.read_text().strip())
        if actual_exit == expected_exit:
            print(f"  PASS {name}: CLI-error exit code matched snapshot")
        else:
            print(f"  FAIL {name}: CLI-error exit code expected {expected_exit}, got {actual_exit}")
            print(f"        stderr: {actual_stderr.strip()[:200]}")
            ok = False

    if not expected_starts_with_path.exists() and not expected_contains_path.exists():
        print(f"  FAIL {name}: no stderr expectation (expected.stderr.starts_with.txt or .contains.txt)")
        ok = False

    if expected_starts_with_path.exists():
        expected_prefix = expected_starts_with_path.read_text().rstrip("\n")
        if expected_prefix and actual_first_line.startswith(expected_prefix):
            print(f"  PASS {name}: CLI-error stderr first line starts with expected prefix")
        else:
            print(f"  FAIL {name}: CLI-error stderr first line missing expected prefix")
            print(f"        expected prefix: {expected_prefix!r}")
            print(f"        actual first:    {actual_first_line!r}")
            ok = False

    if expected_contains_path.exists():
        expected_contains = expected_contains_path.read_text().strip()
        if expected_contains and expected_contains in actual_stderr:
            print(f"  PASS {name}: CLI-error stderr contained expected substring")
        else:
            print(f"  FAIL {name}: CLI-error stderr missing {expected_contains!r}")
            print(f"        actual: {actual_stderr.strip()[:200]}")
            ok = False

    return ok


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
            capture_output=True, text=True, cwd=str(SKILL_ROOT),
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

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
    if result.returncode != 0:
        print(f"  FAIL {name}: triage exited {result.returncode}")
        print(f"        stderr: {result.stderr.strip()}")
        return False

    actual_markdown = normalize_report(output_markdown_path.read_text())
    actual_json = normalize_report_json(json.loads(output_json_path.read_text()), fixture_name=name)

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
    ci_output_dir = Path(f"/tmp/cli-fixture-{name}")
    if ci_output_dir.exists():
        shutil.rmtree(ci_output_dir)
    try:
        token_output_path.unlink()
    except FileNotFoundError:
        pass
    summary_output_path = ci_output_dir / "summary.md"
    output_json_path = ci_output_dir / "report.json"

    cmd = [
        sys.executable,
        str(CLI),
        "ci",
        "--output-dir",
        str(ci_output_dir),
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
            capture_output=True, text=True, cwd=str(SKILL_ROOT),
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

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
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


def run_audit_fixture(fixture_dir: Path, update: bool = False) -> bool:
    name = fixture_dir.name
    spec_path = fixture_dir / "audit.fixture.json"
    expected_stdout_path = fixture_dir / "expected.stdout.txt"
    expected_markdown_path = fixture_dir / "expected.md"
    expected_summary_path = fixture_dir / "expected.summary.md"
    expected_json_path = fixture_dir / "expected.report.json"
    expected_manifest_path = fixture_dir / "expected.manifest.json"
    output_dir = Path("/tmp") / f"{name}-audit-output"

    if output_dir.exists():
        shutil.rmtree(output_dir)

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    cmd = [
        sys.executable,
        str(CLI),
        "audit",
        "--output-dir",
        str(output_dir),
        "--detected-at",
        FIXED_DETECTED_AT,
        "--mode",
        spec.get("mode", "quick"),
    ]

    path_value = spec.get("path")
    if path_value:
        cmd.extend(["--path", str((fixture_dir / path_value).resolve())])
    url_value = spec.get("url")
    if url_value:
        cmd.extend(["--url", url_value])
    framework_value = spec.get("framework")
    if framework_value:
        cmd.extend(["--framework", framework_value])
    runtime_config = spec.get("runtime_config")
    if runtime_config:
        cmd.extend(["--runtime-config", str((fixture_dir / runtime_config).resolve())])
    journey_config = spec.get("journey_config")
    if journey_config:
        cmd.extend(["--journey-config", str((fixture_dir / journey_config).resolve())])
    token_file = spec.get("token_file")
    if token_file:
        cmd.extend(["--token-file", str((fixture_dir / token_file).resolve())])
    baseline_file = spec.get("baseline_file")
    if baseline_file:
        cmd.extend(["--baseline-file", str((fixture_dir / baseline_file).resolve())])
    status_file = spec.get("status_file")
    if status_file:
        cmd.extend(["--status-file", str((fixture_dir / status_file).resolve())])

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL_ROOT))
    if result.returncode != 0:
        print(f"  FAIL {name}: audit command exited {result.returncode}")
        print(f"        stderr: {result.stderr.strip()}")
        return False

    path_aliases = _audit_output_aliases(name, output_dir)
    actual_stdout = normalize_fixture_value(result.stdout.strip(), name, path_aliases=path_aliases)
    actual_markdown = normalize_fixture_value(
        normalize_report((output_dir / "report.md").read_text(encoding="utf-8")),
        name,
        path_aliases=path_aliases,
    )
    actual_summary = normalize_fixture_value(
        normalize_report((output_dir / "summary.md").read_text(encoding="utf-8")),
        name,
        path_aliases=path_aliases,
    )
    actual_json = normalize_report_json(
        json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        fixture_name=name,
    )
    actual_manifest = normalize_fixture_value(
        json.loads((output_dir / "manifest.json").read_text(encoding="utf-8")),
        name,
        path_aliases=path_aliases,
    )

    if update:
        expected_stdout_path.write_text(actual_stdout + "\n", encoding="utf-8")
        expected_markdown_path.write_text(actual_markdown + "\n", encoding="utf-8")
        expected_summary_path.write_text(actual_summary + "\n", encoding="utf-8")
        expected_json_path.write_text(json.dumps(actual_json, indent=2) + "\n", encoding="utf-8")
        expected_manifest_path.write_text(json.dumps(actual_manifest, indent=2) + "\n", encoding="utf-8")
        print(f"  UPDATED {name}: audit package snapshots refreshed")
        shutil.rmtree(output_dir)
        return True

    ok = True
    checks = [
        ("stdout", expected_stdout_path, actual_stdout),
        ("report markdown", expected_markdown_path, actual_markdown),
        ("summary markdown", expected_summary_path, actual_summary),
    ]
    for label, path, actual in checks:
        expected = path.read_text(encoding="utf-8").strip()
        if actual == expected:
            print(f"  PASS {name}: {label} matched snapshot")
        else:
            print(f"  FAIL {name}: {label} differed from {path.name}")
            ok = False

    expected_json = json.loads(expected_json_path.read_text(encoding="utf-8"))
    if actual_json == expected_json:
        print(f"  PASS {name}: report JSON matched snapshot")
    else:
        print(f"  FAIL {name}: report JSON differed from {expected_json_path.name}")
        ok = False

    expected_manifest = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
    if actual_manifest == expected_manifest:
        print(f"  PASS {name}: manifest matched snapshot")
    else:
        print(f"  FAIL {name}: manifest differed from {expected_manifest_path.name}")
        ok = False

    shutil.rmtree(output_dir)
    return ok


def run_fixture(fixture_dir: Path, update: bool = False) -> bool:
    """Returns True if the fixture passes (or was updated), False on failure."""
    if (fixture_dir / "audit.fixture.json").exists():
        return run_audit_fixture(fixture_dir, update=update)
    if (fixture_dir / "cli-error.fixture.json").exists():
        return run_cli_error_fixture(fixture_dir, update=update)
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


def run_invariant_checks() -> bool:
    """Pure-Python invariants we want to guard against regressions even when
    no fixture exercises them.

    Committing machine-specific absolute paths as fixture inputs would break
    portability, so these checks import triage helpers directly and compare
    results at runtime.
    """
    ok = True
    scripts_dir = str(SKILL_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from triage import _repo_relative_path
    except ImportError as exc:
        print(f"  FAIL invariant: could not import triage._repo_relative_path ({exc})")
        return False

    # A concrete file inside this repo — normalized via plain path vs. file://
    # URI vs. percent-encoded file:// URI. All three forms must collapse to the
    # same repo-relative fingerprint, so baselines don't drift when axe-core
    # emits a file-URL form of a path that was previously reported plain.
    concrete = SKILL_ROOT / "fixtures" / "html-basic" / "index.html"
    plain = str(concrete.resolve())
    file_url = "file://" + plain
    # Insert a percent-encoded space into a synthetic path to exercise unquote
    # even though no real repo file has a space — the helper should accept it.
    encoded_url = "file://" + plain.replace("/", "/%2E%2F/").replace("/%2E%2F//", "/")  # no-op; keep plain
    # Simpler: percent-encode a directory separator; unquote must reverse it.
    encoded_url = "file://" + plain.replace("fixtures", "fixture%73")  # `s` → `%73`
    plain_norm = _repo_relative_path(plain)
    file_norm = _repo_relative_path(file_url)
    encoded_norm = _repo_relative_path(encoded_url)
    if plain_norm == file_norm == encoded_norm and not plain_norm.startswith("/"):
        print(f"  PASS invariant: file:// and plain path normalize identically ({plain_norm})")
    else:
        print("  FAIL invariant: file:// normalization diverged from plain-path normalization")
        print(f"        plain:   {plain_norm!r}")
        print(f"        file://: {file_norm!r}")
        print(f"        %-enc:   {encoded_norm!r}")
        ok = False

    # Real web URLs must pass through unchanged — `_repo_relative_path` is
    # only supposed to touch local paths.
    for web in ("http://localhost:3000/page", "https://example.test/x"):
        if _repo_relative_path(web) != web:
            print(f"  FAIL invariant: web URL mutated: {web!r} -> {_repo_relative_path(web)!r}")
            ok = False
    if ok:
        print("  PASS invariant: http/https URLs pass through unchanged")
    return ok


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
            or (d / "expected.manifest.json").exists()
            or (d / "expected.stdout.txt").exists()
            or (d / "expected.exit.txt").exists()
            or (d / "expected.error.txt").exists()
            or (d / "cli-error.fixture.json").exists()
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

    # Runtime invariants (no snapshot) run before the fixture loop so a
    # regression in path-normalization semantics fails loudly even when the
    # downstream fixtures happen to all round-trip correctly.
    if not args.only:
        if run_invariant_checks():
            passed += 1
        else:
            failed += 1

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
