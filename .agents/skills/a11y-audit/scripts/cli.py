#!/usr/bin/env python3
"""
cli.py — CI-oriented orchestration for normalized accessibility reports.

Builds a normalized report from scanner JSON, optionally scopes it to changed
files, renders a PR-friendly markdown summary, and returns deterministic CI
exit codes.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from baseline import load_baseline
from report import (
    blocking_findings,
    filter_report,
    load_changed_files,
    render_pr_summary,
)
from triage import (
    _build_message_lookup,
    _output_dir,
    _now_iso,
    build_markdown_report,
    build_report_data,
    deduplicate,
    generate_manual_review_items,
    load_status_records,
)


def _load_json(path_str: Optional[str]) -> Optional[dict]:
    if not path_str:
        return None
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def _raw_issues(static_data: Optional[dict], runtime_data: Optional[dict], stateful_data: Optional[dict], token_data: Optional[dict]) -> List[dict]:
    issues = []
    for payload in (static_data, runtime_data, stateful_data, token_data):
        if payload:
            issues.extend(payload.get("issues", []))
    return deduplicate(issues)


def main() -> int:
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
    args = parser.parse_args()

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

    try:
        baseline_data = load_baseline(args.baseline_file)
    except FileNotFoundError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Baseline error: {exc}", file=sys.stderr)
        return 3
    except json.JSONDecodeError as exc:
        print(f"Baseline error: {exc}", file=sys.stderr)
        return 3

    detected_at = args.detected_at or _now_iso()
    output_dir = _output_dir(args.output, args.json_output or args.pr_summary_output)
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
    if changed_files:
        report = filter_report(report, changed_files)

    raw_issues = _raw_issues(static_data, runtime_data, stateful_data, token_data)
    message_lookup = _build_message_lookup(raw_issues)
    manual_items = generate_manual_review_items(report, stateful_data)
    step_failures = list((stateful_data or {}).get("step_failures", []))
    markdown_report = build_markdown_report(report, message_lookup, manual_items, step_failures)

    blockers = blocking_findings(
        report,
        fail_on_severity=args.fail_on_severity,
        fail_on_confidence=args.fail_on_confidence,
        fail_on_any_new=args.fail_on_any_new,
        fail_on_manual_findings=args.fail_on_manual_findings,
    )
    pr_summary = render_pr_summary(
        report,
        blockers,
        changed_files=changed_files,
        fail_on_severity=args.fail_on_severity,
        fail_on_confidence=args.fail_on_confidence,
        fail_on_any_new=args.fail_on_any_new,
        fail_on_manual_findings=args.fail_on_manual_findings,
    )

    if args.output:
        Path(args.output).write_text(markdown_report, encoding="utf-8")
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.pr_summary_output:
        Path(args.pr_summary_output).write_text(pr_summary + "\n", encoding="utf-8")

    if not (args.output or args.json_output or args.pr_summary_output):
        print(pr_summary)

    if args.ci:
        return 1 if blockers else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
