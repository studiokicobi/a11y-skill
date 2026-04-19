#!/usr/bin/env python3
"""
report.py — helpers for filtered CI/PR report rendering.
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Iterable, List, Optional, Set


REPORT_GROUPS = ("autofix", "needs_input", "manual_review", "not_checked")
SCANNERS = ("static", "runtime", "stateful", "manual-template", "token")
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
SEVERITY_ORDER = {"n/a": 0, "minor": 1, "moderate": 2, "serious": 3, "critical": 4}


def normalize_repo_path(value: str) -> str:
    normalized = (value or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def load_report(path_str: str) -> dict:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def load_changed_files(path_str: Optional[str]) -> Set[str]:
    if not path_str:
        return set()
    paths = set()
    for raw_line in Path(path_str).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        paths.add(normalize_repo_path(line))
    return paths


def _path_matches(candidate: str, changed_files: Set[str]) -> bool:
    if not candidate:
        return False
    candidate = normalize_repo_path(candidate)
    return any(
        candidate == changed or candidate.endswith("/" + changed) or changed.endswith("/" + candidate)
        for changed in changed_files
    )


def _finding_paths(finding: dict) -> List[str]:
    mapping = finding.get("mapping", {})
    location = finding.get("location", {})
    return [
        normalize_repo_path(mapping.get("source_file", "")),
        normalize_repo_path(location.get("file", "")),
    ]


def finding_in_scope(finding: dict, changed_files: Set[str]) -> bool:
    if not changed_files:
        return True
    if finding.get("triage_group") == "not_checked":
        return False
    return any(_path_matches(candidate, changed_files) for candidate in _finding_paths(finding))


def rebuild_summary(findings: Iterable[dict]) -> dict:
    findings = list(findings)
    active_findings = [
        finding for finding in findings
        if finding.get("status") == "open" and finding.get("triage_group") != "not_checked"
    ]
    not_checked = [finding for finding in findings if finding.get("triage_group") == "not_checked"]
    waived = [finding for finding in findings if finding.get("status") == "waived"]
    return {
        "scanner_detected_issue_count": len(active_findings),
        "auto_fixable_count": sum(1 for finding in active_findings if finding.get("triage_group") == "autofix"),
        "needs_input_count": sum(1 for finding in active_findings if finding.get("triage_group") == "needs_input"),
        "manual_review_count": sum(1 for finding in active_findings if finding.get("triage_group") == "manual_review"),
        "waived_count": len(waived),
        "not_checked_count": len(not_checked),
        "by_scanner": {
            scanner: sum(1 for finding in active_findings if finding.get("scanner") == scanner)
            for scanner in SCANNERS
        },
        "by_confidence": {
            confidence: sum(1 for finding in active_findings if finding.get("confidence") == confidence)
            for confidence in ("high", "medium", "low")
        },
        "status_counts": {
            status: sum(
                1
                for finding in findings
                if finding.get("status") == status and finding.get("triage_group") != "not_checked"
            )
            for status in ("open", "waived", "fixed", "resolved", "stale")
        },
    }


def rebuild_baseline_summary(report: dict) -> dict:
    baseline = report.get("baseline_comparison", {})
    if not baseline.get("baseline_present"):
        return {
            "baseline_present": False,
            "baseline_generated_at": "",
            "summary": {
                "new": 0,
                "unchanged": 0,
                "fixed": 0,
                "resolved": 0,
                "stale": 0,
                "waived": 0,
            },
        }

    summary = {name: 0 for name in ("new", "unchanged", "fixed", "resolved", "stale", "waived")}
    for finding in report.get("findings", []):
        comparison = str(finding.get("comparison", "") or "")
        if comparison in summary:
            summary[comparison] += 1

    return {
        "baseline_present": True,
        "baseline_generated_at": baseline.get("baseline_generated_at", ""),
        "summary": summary,
    }


def filter_report(report: dict, changed_files: Set[str]) -> dict:
    if not changed_files:
        return copy.deepcopy(report)

    filtered = copy.deepcopy(report)
    filtered["findings"] = [
        finding for finding in filtered.get("findings", [])
        if finding_in_scope(finding, changed_files)
    ]
    filtered["summary"] = rebuild_summary(filtered["findings"])
    filtered["baseline_comparison"] = rebuild_baseline_summary(filtered)
    filtered.setdefault("coverage_metadata", {})
    filtered["coverage_metadata"]["not_checked_criteria"] = [
        finding["wcag"][0]
        for finding in filtered["findings"]
        if finding.get("triage_group") == "not_checked" and finding.get("wcag")
    ]
    return filtered


def blocking_findings(
    report: dict,
    fail_on_severity: str = "serious",
    fail_on_confidence: str = "high",
    fail_on_any_new: bool = False,
    fail_on_manual_findings: bool = False,
) -> List[dict]:
    severity_rank = SEVERITY_ORDER[fail_on_severity]
    confidence_rank = CONFIDENCE_ORDER[fail_on_confidence]
    baseline_present = bool(report.get("baseline_comparison", {}).get("baseline_present"))
    blockers = []
    for finding in report.get("findings", []):
        if finding.get("status") != "open" or finding.get("triage_group") == "not_checked":
            continue
        if finding.get("triage_group") == "manual_review" and not fail_on_manual_findings:
            continue

        if fail_on_any_new and baseline_present:
            if finding.get("comparison") == "new":
                blockers.append(finding)
            continue

        if baseline_present and finding.get("comparison") != "new":
            continue
        if SEVERITY_ORDER.get(finding.get("severity", "n/a"), 0) < severity_rank:
            continue
        if CONFIDENCE_ORDER.get(finding.get("confidence", "low"), 0) < confidence_rank:
            continue
        blockers.append(finding)
    return blockers


def _display_location(finding: dict) -> str:
    mapping = finding.get("mapping", {})
    if mapping.get("source_file"):
        if mapping.get("source_line"):
            return f"{mapping['source_file']}:{mapping['source_line']}"
        return str(mapping["source_file"])

    location = finding.get("location", {})
    if location.get("file"):
        if location.get("line"):
            return f"{location['file']}:{location['line']}"
        return str(location["file"])
    url = location.get("url", "")
    step_id = location.get("journey_step_id", "")
    if url and step_id:
        return f"{url} [{step_id}]"
    return url or "(unmapped)"


def render_pr_summary(
    report: dict,
    blockers: List[dict],
    changed_files: Optional[Set[str]] = None,
    fail_on_severity: str = "serious",
    fail_on_confidence: str = "high",
    fail_on_any_new: bool = False,
    fail_on_manual_findings: bool = False,
) -> str:
    changed_files = changed_files or set()
    active_findings = [
        finding for finding in report.get("findings", [])
        if finding.get("status") == "open" and finding.get("triage_group") != "not_checked"
    ]
    non_blocking = [finding for finding in active_findings if finding not in blockers]
    summary = report.get("summary", {})

    lines = ["## Accessibility CI Summary", ""]
    scope_label = "changed files only" if changed_files else "full report"
    if changed_files:
        lines.append(f"- Scope: {scope_label} ({len(changed_files)} file(s))")
    else:
        lines.append(f"- Scope: {scope_label}")
    lines.append(f"- Active findings: {len(active_findings)}")
    lines.append(f"- Blocking findings: {len(blockers)}")
    lines.append(
        f"- Groups: {summary.get('auto_fixable_count', 0)} auto-fixable, "
        f"{summary.get('needs_input_count', 0)} need input, "
        f"{summary.get('manual_review_count', 0)} manual review"
    )
    baseline_summary = report.get("baseline_comparison", {})
    if baseline_summary.get("baseline_present"):
        baseline_parts = [
            f"{name} {count}"
            for name, count in baseline_summary.get("summary", {}).items()
            if count
        ]
        if baseline_parts:
            lines.append(f"- Regression summary: {', '.join(baseline_parts)}")
    lines.append(
        f"- CI threshold: severity >= {fail_on_severity}, confidence >= {fail_on_confidence}, "
        f"any-new={'on' if fail_on_any_new else 'off'}, manual={'on' if fail_on_manual_findings else 'off'}"
    )

    if blockers:
        lines.extend(["", "### Blocking findings"])
        for finding in blockers[:10]:
            comparison = f"[{finding.get('comparison')}]" if finding.get("comparison") else ""
            lines.append(
                f"- [{finding.get('severity')}/{finding.get('confidence')}][{finding.get('triage_group')}]{comparison} "
                f"{finding.get('title')} — {_display_location(finding)}"
            )
    elif not active_findings:
        lines.extend(["", "No active findings in scope."])
    else:
        lines.extend(["", "No blocking findings at the configured threshold."])

    if non_blocking:
        lines.extend(["", "### Non-blocking findings"])
        for finding in non_blocking[:10]:
            comparison = f"[{finding.get('comparison')}]" if finding.get("comparison") else ""
            lines.append(
                f"- [{finding.get('severity')}/{finding.get('confidence')}][{finding.get('triage_group')}]{comparison} "
                f"{finding.get('title')} — {_display_location(finding)}"
            )

    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a PR/CI summary from a normalized report.")
    parser.add_argument("--report", required=True, help="Normalized report JSON")
    parser.add_argument("--summary-output", help="Optional path to write markdown summary")
    parser.add_argument("--changed-files", help="Optional newline-delimited changed files list")
    parser.add_argument("--fail-on-severity", choices=tuple(SEVERITY_ORDER), default="serious")
    parser.add_argument("--fail-on-confidence", choices=tuple(CONFIDENCE_ORDER), default="high")
    parser.add_argument("--fail-on-any-new", action="store_true")
    parser.add_argument("--fail-on-manual-findings", action="store_true")
    parser.add_argument("--ci", action="store_true")
    args = parser.parse_args()

    report = load_report(args.report)
    changed_files = load_changed_files(args.changed_files)
    filtered = filter_report(report, changed_files)
    blockers = blocking_findings(
        filtered,
        fail_on_severity=args.fail_on_severity,
        fail_on_confidence=args.fail_on_confidence,
        fail_on_any_new=args.fail_on_any_new,
        fail_on_manual_findings=args.fail_on_manual_findings,
    )
    summary = render_pr_summary(
        filtered,
        blockers,
        changed_files=changed_files,
        fail_on_severity=args.fail_on_severity,
        fail_on_confidence=args.fail_on_confidence,
        fail_on_any_new=args.fail_on_any_new,
        fail_on_manual_findings=args.fail_on_manual_findings,
    )
    if args.summary_output:
        Path(args.summary_output).write_text(summary + "\n", encoding="utf-8")
    else:
        print(summary)
    return 1 if args.ci and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
