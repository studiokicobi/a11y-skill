#!/usr/bin/env python3
"""
cli.py — public audit and CI orchestration for accessibility reports.

Public workflows:
- `audit`: run scanners, package artifacts, and print a remediation handoff
- `ci`: run or consume scanner outputs, scope to changed files, and return CI exit codes

Legacy flat arguments are still supported for fixture coverage and advanced use.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from baseline import build_baseline, load_baseline
from report import (
    blocking_findings,
    build_scope_metadata,
    filter_report,
    load_changed_files,
    render_pr_summary,
)
from triage import (
    _build_message_lookup,
    _now_iso,
    build_markdown_report,
    build_outcome_summary,
    build_report_data,
    deduplicate,
    generate_manual_review_items,
    load_status_records,
)


SCRIPT_DIR = Path(__file__).resolve().parent
STATIC_SCANNER = SCRIPT_DIR / "a11y_scan.py"
RUNTIME_SCANNER = SCRIPT_DIR / "a11y_runtime.js"
STATEFUL_SCANNER = SCRIPT_DIR / "a11y_stateful.js"
TOKEN_SCANNER = SCRIPT_DIR / "tokens.py"
DEFAULT_ARTIFACT_ROOT = Path(".artifacts") / "a11y"


def _load_json(path_str: Optional[str]) -> Optional[dict]:
    if not path_str:
        return None
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def _raw_issues(
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    token_data: Optional[dict],
) -> List[dict]:
    issues = []
    for payload in (static_data, runtime_data, stateful_data, token_data):
        if payload:
            issues.extend(payload.get("issues", []))
    return deduplicate(issues)


def _parse_detected_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _run_id(detected_at: str) -> str:
    try:
        return _parse_detected_at(detected_at).strftime("%Y%m%dT%H%M%SZ")
    except ValueError:
        fallback = "".join(ch if ch.isalnum() else "-" for ch in detected_at)
        return fallback.strip("-") or "run"


def _resolve_output_dir(output_dir: Optional[str], detected_at: str) -> Path:
    if output_dir:
        path = Path(output_dir)
    else:
        path = DEFAULT_ARTIFACT_ROOT / _run_id(detected_at)
    return path.resolve()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _relative_artifact(output_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(output_dir.resolve()).as_posix()


def _prepare_output_tree(output_dir: Path) -> Dict[str, Path]:
    paths = {
        "root": output_dir,
        "scanners": output_dir / "scanners",
        "evidence": output_dir / "evidence",
        "screenshots": output_dir / "evidence" / "screenshots",
        "dom": output_dir / "evidence" / "dom",
        "focus": output_dir / "evidence" / "focus",
        "inputs": output_dir / "inputs",
        "report_md": output_dir / "report.md",
        "report_json": output_dir / "report.json",
        "summary_md": output_dir / "summary.md",
        "manifest_json": output_dir / "manifest.json",
    }
    for key in ("root", "scanners", "evidence", "screenshots", "dom", "focus", "inputs"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def _run_command(cmd: List[str], label: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    detail = stderr or stdout or f"exited with code {result.returncode}"
    raise RuntimeError(f"{label} failed: {detail}")


def _copy_json_input(source: Path, dest: Path) -> dict:
    shutil.copyfile(source, dest)
    return json.loads(dest.read_text(encoding="utf-8"))


def _copy_named_input(source: Optional[str], dest_dir: Path, dest_name: str) -> Optional[str]:
    if not source:
        return None
    source_path = Path(source).resolve()
    suffix = "".join(source_path.suffixes)
    dest_path = dest_dir / f"{dest_name}{suffix}"
    shutil.copyfile(source_path, dest_path)
    return dest_path.name if dest_path.is_file() else None


def _run_static_scan(target_path: str, output_path: Path, framework: str) -> dict:
    cmd = [
        sys.executable,
        str(STATIC_SCANNER),
        target_path,
        "--quiet",
        "--output",
        str(output_path),
    ]
    if framework:
        cmd.extend(["--framework", framework])
    _run_command(cmd, "Static scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_runtime_scan(url: Optional[str], runtime_config: Optional[str], output_path: Path, screenshot_dir: Path) -> dict:
    cmd = [
        "node",
        str(RUNTIME_SCANNER),
        "--output",
        str(output_path),
        "--screenshot-dir",
        str(screenshot_dir),
    ]
    if url:
        cmd.extend(["--url", url])
    if runtime_config:
        cmd.extend(["--config", runtime_config])
    _run_command(cmd, "Runtime scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_stateful_scan(journey_config: str, output_path: Path, screenshot_dir: Path) -> dict:
    cmd = [
        "node",
        str(STATEFUL_SCANNER),
        "--config",
        journey_config,
        "--output",
        str(output_path),
        "--screenshot-dir",
        str(screenshot_dir),
    ]
    _run_command(cmd, "Stateful scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_token_scan(token_file: str, output_path: Path) -> dict:
    cmd = [
        sys.executable,
        str(TOKEN_SCANNER),
        token_file,
        "--output",
        str(output_path),
    ]
    _run_command(cmd, "Token scan")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _artifact_index(paths: Dict[str, Path], scanner_payloads: Dict[str, Optional[dict]]) -> List[str]:
    artifacts = [
        _relative_artifact(paths["root"], paths["report_json"]),
        _relative_artifact(paths["root"], paths["summary_md"]),
        _relative_artifact(paths["root"], paths["manifest_json"]),
    ]
    for scanner_name in ("static", "runtime", "stateful", "tokens"):
        if scanner_payloads.get(scanner_name):
            filename = "tokens.json" if scanner_name == "tokens" else f"{scanner_name}.json"
            artifacts.append(f"scanners/{filename}")
    if any(paths["screenshots"].iterdir()):
        artifacts.append(_relative_artifact(paths["root"], paths["screenshots"]))
    return artifacts


def _build_render_context(
    mode_label: str,
    artifact_paths: List[str],
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    token_data: Optional[dict],
    scope_metadata: Optional[dict] = None,
) -> dict:
    scanners_ran = []
    if static_data:
        scanners_ran.append("static")
    if runtime_data:
        scanners_ran.append("runtime")
    if stateful_data:
        scanners_ran.append("stateful")
    if token_data:
        scanners_ran.append("token")
    return {
        "mode": mode_label,
        "artifact_paths": artifact_paths,
        "scanners_ran": scanners_ran,
        "excluded_low_confidence_count": int((scope_metadata or {}).get("excluded_low_confidence_count", 0) or 0),
    }


def _render_outputs(
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    token_data: Optional[dict],
    baseline_data: Optional[dict],
    status_records: List[dict],
    changed_files,
    detected_at: str,
    output_dir: Path,
    mode_label: str,
    artifact_paths: List[str],
    fail_on_severity: str,
    fail_on_confidence: str,
    fail_on_any_new: bool,
    fail_on_manual_findings: bool,
    ci_mode: bool,
) -> dict:
    report = build_report_data(
        static_data,
        runtime_data,
        stateful_data,
        token_data,
        baseline_data,
        output_dir,
        detected_at,
        status_records,
    )
    scope_metadata = build_scope_metadata(report, changed_files)
    if changed_files:
        report = filter_report(report, changed_files)

    raw_issues = _raw_issues(static_data, runtime_data, stateful_data, token_data)
    message_lookup = _build_message_lookup(raw_issues)
    manual_items = generate_manual_review_items(report, stateful_data)
    step_failures = list((stateful_data or {}).get("step_failures", []))
    render_context = _build_render_context(
        mode_label,
        artifact_paths,
        static_data,
        runtime_data,
        stateful_data,
        token_data,
        scope_metadata=scope_metadata,
    )
    markdown_report = build_markdown_report(
        report,
        message_lookup,
        manual_items,
        step_failures,
        render_context=render_context,
    )

    blockers = blocking_findings(
        report,
        fail_on_severity=fail_on_severity,
        fail_on_confidence=fail_on_confidence,
        fail_on_any_new=fail_on_any_new,
        fail_on_manual_findings=fail_on_manual_findings,
    )
    summary = render_pr_summary(
        report,
        blockers,
        changed_files=changed_files,
        fail_on_severity=fail_on_severity,
        fail_on_confidence=fail_on_confidence,
        fail_on_any_new=fail_on_any_new,
        fail_on_manual_findings=fail_on_manual_findings,
        scope_metadata=scope_metadata,
        ci_mode=ci_mode,
    )
    return {
        "report": report,
        "markdown": markdown_report,
        "summary": summary,
        "blockers": blockers,
        "scope_metadata": scope_metadata,
        "manual_items": manual_items,
        "outcome_summary": build_outcome_summary(report, manual_items),
    }


def _recommended_first_step(outcome_summary: dict) -> Optional[str]:
    auto_count = int(outcome_summary.get("auto_count", 0) or 0)
    input_count = int(outcome_summary.get("input_count", 0) or 0)
    manual_review_count = int(outcome_summary.get("manual_review_count", 0) or 0)
    guided_check_count = int(outcome_summary.get("guided_check_count", 0) or 0)
    active_finding_count = int(outcome_summary.get("active_finding_count", 0) or 0)

    if active_finding_count == 0:
        return None
    if auto_count > 0:
        return 'Recommended first step: say "apply the safe fixes". Open the report for all available next actions.'
    if input_count > 0:
        return 'Recommended first step: say "walk me through the decisions". Open the report for all available next actions.'
    if manual_review_count > 0 and guided_check_count > 0:
        return (
            'Recommended first step: say "give me the checklist". Say "show me the manual findings" for just the '
            'scanner-flagged items. Open the report for the full action menu.'
        )
    if manual_review_count > 0:
        return 'Recommended first step: say "show me the manual findings". Open the report for all available next actions.'
    return None


def _write_manifest(
    manifest_path: Path,
    run_kind: str,
    mode_label: str,
    detected_at: str,
    output_dir: Path,
    report: dict,
    scanner_payloads: Dict[str, Optional[dict]],
    input_copies: Dict[str, str],
    scope_metadata: dict,
    baseline_output: Optional[str] = None,
) -> None:
    artifacts = {
        "report_markdown": "report.md",
        "report_json": "report.json",
        "summary_markdown": "summary.md",
        "scanner_outputs": {},
    }
    for scanner_name in ("static", "runtime", "stateful", "tokens"):
        if scanner_payloads.get(scanner_name):
            filename = "tokens.json" if scanner_name == "tokens" else f"{scanner_name}.json"
            artifacts["scanner_outputs"][scanner_name] = f"scanners/{filename}"
    if any((output_dir / "evidence" / "screenshots").iterdir()):
        artifacts["screenshots"] = "evidence/screenshots"

    manifest = {
        "run_id": output_dir.name,
        "run_kind": run_kind,
        "mode": mode_label,
        "generated_at": detected_at,
        "target": report.get("target", ""),
        "framework": report.get("framework", ""),
        "summary": report.get("summary", {}),
        "baseline_comparison": report.get("baseline_comparison", {}),
        "scope_metadata": scope_metadata,
        "artifacts": artifacts,
        "inputs": input_copies,
        "scanners_ran": [
            scanner_name
            for scanner_name in ("static", "runtime", "stateful", "tokens")
            if scanner_payloads.get(scanner_name)
        ],
    }
    if baseline_output:
        manifest["baseline_output"] = baseline_output
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _add_shared_source_args(parser: argparse.ArgumentParser, include_raw: bool, include_changed_files: bool) -> None:
    parser.add_argument("--path", type=str, help="Source path for static scanning")
    parser.add_argument("--url", type=str, help="Runtime URL to scan")
    parser.add_argument("--framework", type=str, default="auto", help="Static framework override")
    parser.add_argument("--runtime-config", type=str, help="Optional runtime JSON/YAML config")
    parser.add_argument("--journey-config", type=str, help="Optional stateful journey JSON/YAML config")
    parser.add_argument("--token-file", type=str, help="Optional token JSON input")
    parser.add_argument("--baseline-file", type=str, help="Optional baseline JSON")
    parser.add_argument("--status-file", type=str, help="Optional status/waiver JSON")
    if include_changed_files:
        parser.add_argument("--changed-files", type=str, help="Optional newline-delimited changed files list")
    parser.add_argument("--output-dir", type=str, help="Artifact output directory")
    parser.add_argument("--detected-at", type=str, help="ISO timestamp override")
    if include_raw:
        parser.add_argument("--static", type=str, help="Path to static scanner JSON")
        parser.add_argument("--runtime", type=str, help="Path to runtime scanner JSON")
        parser.add_argument("--stateful", type=str, help="Path to stateful scanner JSON")
        parser.add_argument("--tokens", type=str, help="Path to token scanner JSON")


def _build_public_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Accessibility audit workflow orchestrator")
    subparsers = parser.add_subparsers(dest="command", metavar="{audit,ci}")

    audit = subparsers.add_parser("audit", help="Run a local accessibility audit and package the results")
    _add_shared_source_args(audit, include_raw=False, include_changed_files=False)
    audit.add_argument("--mode", choices=("quick", "full"), default="quick")
    audit.add_argument("--write-baseline", type=str, help="Optional path to write a baseline JSON")
    audit.add_argument("--update-baseline", action="store_true", help="Write a fresh baseline back to --baseline-file")

    ci = subparsers.add_parser("ci", help="Run CI/PR-friendly audit output with deterministic exit codes")
    _add_shared_source_args(ci, include_raw=True, include_changed_files=True)
    ci.add_argument("--ci", action="store_true", help="Return CI exit codes")
    ci.add_argument("--fail-on-severity", choices=("minor", "moderate", "serious", "critical"), default="serious")
    ci.add_argument("--fail-on-confidence", choices=("low", "medium", "high"), default="high")
    ci.add_argument("--fail-on-any-new", action="store_true")
    ci.add_argument("--fail-on-manual-findings", action="store_true")

    promote = subparsers.add_parser("promote-baseline", help=argparse.SUPPRESS)
    promote.add_argument("--report", required=True, help="Normalized report JSON")
    promote.add_argument("--baseline-file", required=True, help="Path to write baseline JSON")
    subparsers._choices_actions = [
        action for action in subparsers._choices_actions
        if getattr(action, "dest", None) != "promote-baseline"
    ]

    return parser


def _legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Accessibility CI/PR report orchestrator")
    parser.add_argument("--static", type=str, help="Path to static scanner JSON")
    parser.add_argument("--runtime", type=str, help="Path to runtime scanner JSON")
    parser.add_argument("--stateful", type=str, help="Path to stateful scanner JSON")
    parser.add_argument("--tokens", type=str, help="Path to token scanner JSON")
    parser.add_argument("--baseline-file", type=str, help="Optional baseline JSON")
    parser.add_argument("--status-file", type=str, help="Optional status/waiver JSON")
    parser.add_argument("--output", type=str, help="Optional markdown report output")
    parser.add_argument("--json-output", type=str, help="Optional normalized JSON output")
    parser.add_argument("--pr-summary-output", type=str, help="Optional PR summary markdown output")
    parser.add_argument("--changed-files", type=str, help="Optional newline-delimited changed files list")
    parser.add_argument("--detected-at", type=str, help="ISO timestamp override")
    parser.add_argument("--ci", action="store_true", help="Return CI exit codes")
    parser.add_argument("--fail-on-severity", choices=("minor", "moderate", "serious", "critical"), default="serious")
    parser.add_argument("--fail-on-confidence", choices=("low", "medium", "high"), default="high")
    parser.add_argument("--fail-on-any-new", action="store_true")
    parser.add_argument("--fail-on-manual-findings", action="store_true")
    return parser


def _load_baseline_or_error(path_str: Optional[str]):
    try:
        return load_baseline(path_str), None
    except FileNotFoundError as exc:
        return None, (2, f"Configuration error: {exc}")
    except ValueError as exc:
        return None, (3, f"Baseline error: {exc}")
    except json.JSONDecodeError as exc:
        return None, (3, f"Baseline error: {exc}")


def _load_status_or_error(path_str: Optional[str]):
    try:
        return load_status_records(path_str), None
    except FileNotFoundError as exc:
        return None, (2, f"Configuration error: {exc}")
    except json.JSONDecodeError as exc:
        return None, (2, f"Configuration error: {exc}")


def _collect_audit_payloads(args, paths: Dict[str, Path]) -> Dict[str, Optional[dict]]:
    payloads: Dict[str, Optional[dict]] = {
        "static": None,
        "runtime": None,
        "stateful": None,
        "tokens": None,
    }
    if args.path:
        payloads["static"] = _run_static_scan(args.path, paths["scanners"] / "static.json", args.framework)
    if args.url or args.runtime_config:
        payloads["runtime"] = _run_runtime_scan(
            args.url,
            args.runtime_config,
            paths["scanners"] / "runtime.json",
            paths["screenshots"],
        )
    if args.journey_config:
        payloads["stateful"] = _run_stateful_scan(
            args.journey_config,
            paths["scanners"] / "stateful.json",
            paths["screenshots"],
        )
    if args.token_file:
        payloads["tokens"] = _run_token_scan(args.token_file, paths["scanners"] / "tokens.json")
    if not any(payloads.values()):
        raise RuntimeError("Provide at least one of --path, --url, --runtime-config, --journey-config, or --token-file.")
    return payloads


def _collect_ci_payloads(args, paths: Dict[str, Path]) -> Dict[str, Optional[dict]]:
    payloads: Dict[str, Optional[dict]] = {
        "static": None,
        "runtime": None,
        "stateful": None,
        "tokens": None,
    }

    if args.static:
        payloads["static"] = _copy_json_input(Path(args.static).resolve(), paths["scanners"] / "static.json")
    elif args.path:
        payloads["static"] = _run_static_scan(args.path, paths["scanners"] / "static.json", args.framework)

    if args.runtime:
        payloads["runtime"] = _copy_json_input(Path(args.runtime).resolve(), paths["scanners"] / "runtime.json")
    elif args.url or args.runtime_config:
        payloads["runtime"] = _run_runtime_scan(
            args.url,
            args.runtime_config,
            paths["scanners"] / "runtime.json",
            paths["screenshots"],
        )

    if args.stateful:
        payloads["stateful"] = _copy_json_input(Path(args.stateful).resolve(), paths["scanners"] / "stateful.json")
    elif args.journey_config:
        payloads["stateful"] = _run_stateful_scan(
            args.journey_config,
            paths["scanners"] / "stateful.json",
            paths["screenshots"],
        )

    if args.tokens:
        payloads["tokens"] = _copy_json_input(Path(args.tokens).resolve(), paths["scanners"] / "tokens.json")
    elif args.token_file:
        payloads["tokens"] = _run_token_scan(args.token_file, paths["scanners"] / "tokens.json")

    if not any(payloads.values()):
        raise RuntimeError(
            "Provide scanner JSON via --static/--runtime/--stateful/--tokens or source inputs via --path/--url/--runtime-config/--journey-config/--token-file."
        )
    return payloads


def _write_outputs(paths: Dict[str, Path], markdown_report: str, report: dict, summary: str) -> None:
    paths["report_md"].write_text(markdown_report, encoding="utf-8")
    paths["report_json"].write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    paths["summary_md"].write_text(summary + "\n", encoding="utf-8")


def _audit_main(argv: List[str]) -> int:
    parser = _build_public_parser()
    args = parser.parse_args(argv)
    detected_at = args.detected_at or _now_iso()
    output_dir = _resolve_output_dir(args.output_dir, detected_at)
    paths = _prepare_output_tree(output_dir)

    baseline_data, baseline_error = _load_baseline_or_error(args.baseline_file)
    if baseline_error:
        print(baseline_error[1], file=sys.stderr)
        return baseline_error[0]

    status_records, status_error = _load_status_or_error(args.status_file)
    if status_error:
        print(status_error[1], file=sys.stderr)
        return status_error[0]

    try:
        payloads = _collect_audit_payloads(args, paths)
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    input_copies = {}
    for source, dest_name, key in (
        (args.runtime_config, "runtime.config", "runtime_config"),
        (args.journey_config, "journey.config", "journey_config"),
        (args.token_file, "tokens", "token_file"),
        (args.baseline_file, "baseline", "baseline_file"),
        (args.status_file, "status", "status_file"),
    ):
        copied = _copy_named_input(source, paths["inputs"], dest_name)
        if copied:
            input_copies[key] = f"inputs/{copied}"

    artifact_paths = _artifact_index(paths, payloads)
    outputs = _render_outputs(
        payloads["static"],
        payloads["runtime"],
        payloads["stateful"],
        payloads["tokens"],
        baseline_data,
        status_records or [],
        set(),
        detected_at,
        paths["root"],
        args.mode,
        artifact_paths,
        fail_on_severity="serious",
        fail_on_confidence="high",
        fail_on_any_new=False,
        fail_on_manual_findings=False,
        ci_mode=False,
    )
    _write_outputs(paths, outputs["markdown"], outputs["report"], outputs["summary"])

    baseline_output_path = None
    if args.write_baseline:
        baseline_output_path = Path(args.write_baseline).resolve()
    elif args.update_baseline:
        if not args.baseline_file:
            print("Configuration error: --update-baseline requires --baseline-file", file=sys.stderr)
            return 2
        baseline_output_path = Path(args.baseline_file).resolve()

    baseline_output_display = None
    if baseline_output_path:
        baseline_output_path.write_text(
            json.dumps(build_baseline(outputs["report"]), indent=2) + "\n",
            encoding="utf-8",
        )
        baseline_output_display = _display_path(baseline_output_path)

    _write_manifest(
        paths["manifest_json"],
        run_kind="audit",
        mode_label=args.mode,
        detected_at=detected_at,
        output_dir=paths["root"],
        report=outputs["report"],
        scanner_payloads=payloads,
        input_copies=input_copies,
        scope_metadata=outputs["scope_metadata"],
        baseline_output=baseline_output_display,
    )

    outcome_summary = outputs["outcome_summary"]
    print(outcome_summary["outcome_body"])
    print(f"Full report: {_display_path(paths['report_md'])}")
    recommended_first_step = _recommended_first_step(outcome_summary)
    if recommended_first_step:
        print(recommended_first_step)
    if baseline_output_display:
        print(f"Baseline: {baseline_output_display}")
    return 0


def _ci_main(argv: List[str]) -> int:
    parser = _build_public_parser()
    args = parser.parse_args(argv)
    detected_at = args.detected_at or _now_iso()
    output_dir = _resolve_output_dir(args.output_dir, detected_at)
    paths = _prepare_output_tree(output_dir)

    baseline_data, baseline_error = _load_baseline_or_error(args.baseline_file)
    if baseline_error:
        print(baseline_error[1], file=sys.stderr)
        return baseline_error[0]

    status_records, status_error = _load_status_or_error(args.status_file)
    if status_error:
        print(status_error[1], file=sys.stderr)
        return status_error[0]

    try:
        payloads = _collect_ci_payloads(args, paths)
    except RuntimeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    changed_files = load_changed_files(args.changed_files)
    input_copies = {}
    for source, dest_name, key in (
        (args.runtime_config, "runtime.config", "runtime_config"),
        (args.journey_config, "journey.config", "journey_config"),
        (args.token_file, "tokens", "token_file"),
        (args.baseline_file, "baseline", "baseline_file"),
        (args.status_file, "status", "status_file"),
        (args.changed_files, "changed-files", "changed_files"),
    ):
        copied = _copy_named_input(source, paths["inputs"], dest_name)
        if copied:
            input_copies[key] = f"inputs/{copied}"

    artifact_paths = _artifact_index(paths, payloads)
    outputs = _render_outputs(
        payloads["static"],
        payloads["runtime"],
        payloads["stateful"],
        payloads["tokens"],
        baseline_data,
        status_records or [],
        changed_files,
        detected_at,
        paths["root"],
        "ci",
        artifact_paths,
        fail_on_severity=args.fail_on_severity,
        fail_on_confidence=args.fail_on_confidence,
        fail_on_any_new=args.fail_on_any_new,
        fail_on_manual_findings=args.fail_on_manual_findings,
        ci_mode=True,
    )
    _write_outputs(paths, outputs["markdown"], outputs["report"], outputs["summary"])
    _write_manifest(
        paths["manifest_json"],
        run_kind="ci",
        mode_label="ci",
        detected_at=detected_at,
        output_dir=paths["root"],
        report=outputs["report"],
        scanner_payloads=payloads,
        input_copies=input_copies,
        scope_metadata=outputs["scope_metadata"],
    )

    print(f"Accessibility check: {len(outputs['blockers'])} blocking issue(s). Summary: {_display_path(paths['summary_md'])}")
    if args.ci:
        return 1 if outputs["blockers"] else 0
    return 0


def _promote_baseline_main(argv: List[str]) -> int:
    parser = _build_public_parser()
    args = parser.parse_args(argv)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    baseline = build_baseline(report)
    Path(args.baseline_file).write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"Baseline written to {args.baseline_file}")
    return 0


def _legacy_main(argv: List[str]) -> int:
    parser = _legacy_parser()
    args = parser.parse_args(argv)

    if not (args.static or args.runtime or args.stateful or args.tokens):
        print("Error: provide at least one of --static, --runtime, --stateful, or --tokens", file=sys.stderr)
        return 2

    try:
        static_data = _load_json(args.static)
        runtime_data = _load_json(args.runtime)
        stateful_data = _load_json(args.stateful)
        token_data = _load_json(args.tokens)
        status_records = load_status_records(args.status_file)
        changed_files = load_changed_files(args.changed_files)
    except FileNotFoundError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    baseline_data, baseline_error = _load_baseline_or_error(args.baseline_file)
    if baseline_error:
        print(baseline_error[1], file=sys.stderr)
        return baseline_error[0]

    detected_at = args.detected_at or _now_iso()
    output_dir = (Path(args.output or args.json_output or args.pr_summary_output).parent.resolve()
                  if (args.output or args.json_output or args.pr_summary_output)
                  else Path.cwd().resolve())
    artifact_paths = []
    if args.json_output:
        artifact_paths.append(Path(args.json_output).name)
    if args.pr_summary_output:
        artifact_paths.append(Path(args.pr_summary_output).name)
    outputs = _render_outputs(
        static_data,
        runtime_data,
        stateful_data,
        token_data,
        baseline_data,
        status_records,
        changed_files,
        detected_at,
        output_dir,
        "legacy",
        artifact_paths,
        fail_on_severity=args.fail_on_severity,
        fail_on_confidence=args.fail_on_confidence,
        fail_on_any_new=args.fail_on_any_new,
        fail_on_manual_findings=args.fail_on_manual_findings,
        ci_mode=True,
    )

    if args.output:
        Path(args.output).write_text(outputs["markdown"], encoding="utf-8")
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(outputs["report"], indent=2) + "\n", encoding="utf-8")
    if args.pr_summary_output:
        Path(args.pr_summary_output).write_text(outputs["summary"] + "\n", encoding="utf-8")

    if not (args.output or args.json_output or args.pr_summary_output):
        print(outputs["summary"])

    if args.ci:
        return 1 if outputs["blockers"] else 0
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _build_public_parser().print_help()
        return 0
    if argv[0] in {"-h", "--help"}:
        _build_public_parser().parse_args(argv)
        return 0
    if argv[0] == "audit":
        return _audit_main(argv)
    if argv and argv[0] == "ci":
        return _ci_main(argv)
    if argv and argv[0] == "promote-baseline":
        return _promote_baseline_main(argv)
    if argv and not argv[0].startswith("-"):
        _build_public_parser().parse_args(argv)
        return 0
    return _legacy_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
