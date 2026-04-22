#!/usr/bin/env python3
"""
report.py — helpers for filtered CI/PR report rendering.
"""

import argparse
import copy
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


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


def build_scope_metadata(report: dict, changed_files: Set[str]) -> dict:
    if not changed_files:
        return {
            "excluded_total_count": 0,
            "excluded_low_confidence_count": 0,
        }

    excluded = [
        finding for finding in report.get("findings", [])
        if finding.get("status") == "open"
        and finding.get("triage_group") != "not_checked"
        and not finding_in_scope(finding, changed_files)
    ]
    return {
        "excluded_total_count": len(excluded),
        "excluded_low_confidence_count": sum(
            1
            for finding in excluded
            if finding.get("mapping", {}).get("confidence") == "low"
        ),
    }


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


def _display_path(path_value: str) -> str:
    if not path_value:
        return path_value
    if "://" in path_value:
        return path_value
    try:
        candidate = Path(path_value)
    except (TypeError, ValueError):
        return path_value
    if not candidate.is_absolute():
        return path_value
    try:
        return str(candidate.relative_to(Path.cwd()))
    except ValueError:
        return path_value


def _display_location(finding: dict) -> str:
    mapping = finding.get("mapping", {})
    if mapping.get("source_file"):
        source_file = _display_path(mapping["source_file"])
        if mapping.get("source_line"):
            return f"{source_file}:{mapping['source_line']}"
        return source_file

    location = finding.get("location", {})
    if location.get("file"):
        file_display = _display_path(location["file"])
        if location.get("line"):
            return f"{file_display}:{location['line']}"
        return file_display
    url = location.get("url", "")
    step_id = location.get("journey_step_id", "")
    if url and step_id:
        return f"{url} [{step_id}]"
    return url or "(unmapped)"


def _blocking_reason(
    finding: dict,
    baseline_present: bool,
    fail_on_any_new: bool,
    fail_on_manual_findings: bool,
) -> str:
    if baseline_present and fail_on_any_new and finding.get("comparison") == "new":
        return "blocking because it is new and fail-on-any-new is enabled"
    if finding.get("triage_group") == "manual_review" and fail_on_manual_findings:
        return "blocking because manual-review findings are configured to fail CI"
    return (
        f"blocking because severity {finding.get('severity')} and confidence "
        f"{finding.get('confidence')} meet the configured threshold"
    )


def render_pr_summary(
    report: dict,
    blockers: List[dict],
    changed_files: Optional[Set[str]] = None,
    fail_on_severity: str = "serious",
    fail_on_confidence: str = "high",
    fail_on_any_new: bool = False,
    fail_on_manual_findings: bool = False,
    scope_metadata: Optional[dict] = None,
    ci_mode: bool = True,
) -> str:
    changed_files = changed_files or set()
    scope_metadata = scope_metadata or {}
    active_findings = [
        finding for finding in report.get("findings", [])
        if finding.get("status") == "open" and finding.get("triage_group") != "not_checked"
    ]
    non_blocking = [finding for finding in active_findings if finding not in blockers]
    summary = report.get("summary", {})
    baseline_present = bool(report.get("baseline_comparison", {}).get("baseline_present"))

    lines = [("## Accessibility check" if ci_mode else "## Accessibility Summary"), ""]
    scope_label = "changed files only" if changed_files else "full report"
    if changed_files:
        lines.append(f"- Scope: {scope_label} ({len(changed_files)} file(s))")
    else:
        lines.append(f"- Scope: {scope_label}")
    lines.append(f"- Active findings: {len(active_findings)}")
    lines.append(f"- Blocking findings: {len(blockers)}")
    lines.append(
        f"- Buckets: {summary.get('auto_fixable_count', 0)} safe to fix, "
        f"{summary.get('needs_input_count', 0)} need decisions, "
        f"{summary.get('manual_review_count', 0)} to review manually"
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
        f"- {'Failing threshold' if ci_mode else 'Threshold'}: severity >= {fail_on_severity}, confidence >= {fail_on_confidence}, "
        f"any-new={'on' if fail_on_any_new else 'off'}, manual={'on' if fail_on_manual_findings else 'off'}"
    )
    excluded_low_confidence_count = int(scope_metadata.get("excluded_low_confidence_count", 0) or 0)
    if changed_files and excluded_low_confidence_count:
        label = "finding" if excluded_low_confidence_count == 1 else "findings"
        lines.append(
            f"- Excluded from scope: {excluded_low_confidence_count} {label} with low-confidence mapping"
        )

    if blockers:
        lines.extend(["", "### Blocking findings"])
        for finding in blockers[:10]:
            comparison = f"[{finding.get('comparison')}]" if finding.get("comparison") else ""
            lines.append(
                f"- [{finding.get('severity')}/{finding.get('confidence')}][{finding.get('triage_group')}]{comparison} "
                f"{finding.get('title')} — {_display_location(finding)} "
                f"({_blocking_reason(finding, baseline_present, fail_on_any_new, fail_on_manual_findings)})"
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


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _markdown_location(finding: dict) -> str:
    location = finding["location"]
    if location["file"]:
        file_display = _display_path(location["file"])
        return f"`{file_display}:{location['line']}`" if location["line"] else f"`{file_display}`"
    if location["journey_step_id"]:
        return f"`{location['url']}` after step `{location['journey_step_id']}`"
    return f"`{location['url']}`"


def _render_guided_checklist(items: List[dict], step_failures: List[dict]) -> List[str]:
    lines = []
    if step_failures:
        lines.append("Recorded journey step failures:")
        for failure in step_failures:
            lines.append(
                f"- `{failure.get('journey_step_id', '')}` ({failure.get('action', '')}) — {failure.get('message', '')}"
            )
        lines.append("")

    for index, item in enumerate(items, start=1):
        lines.append(f"#### {index}. {item['title']}")
        lines.append(f"**Capability**: `{item['capability']}`")
        lines.append(f"**WCAG**: {', '.join(item['wcag'])}")
        lines.append(f"**Context**: {item['context']}")
        lines.append("**How to test**:")
        for step in item["steps"]:
            lines.append(f"- [ ] {step}")
        lines.append("**Expected result**:")
        for expected in item["expected"]:
            lines.append(f"- [ ] {expected}")
        lines.append("")
    return lines


def _render_not_checked_lines(findings: List[dict]) -> List[str]:
    lines = []
    for finding in findings:
        criterion = finding["wcag"][0] if finding["wcag"] else ""
        note = finding["proposed_fix"]["notes"]
        if note:
            lines.append(f"- {criterion} — {finding['title']} — {note}")
        else:
            lines.append(f"- {criterion} — {finding['title']}")
    return lines


def _finding_message(finding: dict, message_lookup: Dict[str, str]) -> str:
    return message_lookup.get(finding["fingerprint"], "") or finding["title"]


def _comparison_value(finding: dict) -> str:
    return str(finding.get("comparison", "") or "")


def _blast_radius_value(finding: dict) -> str:
    blast_radius = finding.get("blast_radius")
    if isinstance(blast_radius, dict):
        return str(blast_radius.get("summary", "") or "")
    return ""


def _snapshot_lines(report: dict, render_context: Optional[dict]) -> List[str]:
    render_context = render_context or {}
    scanners_ran = list(render_context.get("scanners_ran", []))
    artifact_paths = list(render_context.get("artifact_paths", []))
    excluded_low_confidence_count = int(render_context.get("excluded_low_confidence_count", 0) or 0)

    lines = [
        "## Snapshot",
        f"- Target: {_display_path(report['target'])}",
        f"- Framework: {report['framework']}",
        f"- Standard: {report['standard']}",
    ]
    mode = str(render_context.get("mode", "") or "").strip()
    if mode:
        lines.append(f"- Mode: {mode}")
    if scanners_ran:
        lines.append(f"- Checked: {', '.join(scanners_ran)}")

    by_scanner = report["summary"].get("by_scanner", {})
    scanner_parts = [
        f"{scanner} {count}"
        for scanner, count in by_scanner.items()
        if count
    ]
    if scanner_parts:
        lines.append(f"- Findings by source: {', '.join(scanner_parts)}")

    baseline_comparison = report.get("baseline_comparison", {})
    if baseline_comparison.get("baseline_present"):
        baseline_parts = [
            f"{name} {count}"
            for name, count in baseline_comparison.get("summary", {}).items()
            if count
        ]
        lines.append(f"- Baseline: {', '.join(baseline_parts) if baseline_parts else 'present'}")
    else:
        lines.append("- Baseline: none")

    by_confidence = report["summary"].get("by_confidence", {})
    confidence_parts = [
        f"{confidence} {count}"
        for confidence, count in by_confidence.items()
        if count
    ]
    if confidence_parts:
        lines.append(f"- Confidence: {', '.join(confidence_parts)}")

    if excluded_low_confidence_count:
        label = "finding" if excluded_low_confidence_count == 1 else "findings"
        lines.append(
            f"- Excluded from changed-files scope: {excluded_low_confidence_count} {label} with low-confidence mapping"
        )

    if artifact_paths:
        lines.append("Artifacts:")
        for artifact in artifact_paths:
            lines.append(f"- `{artifact}`")

    lines.append("")
    return lines


def _format_outcome_count(value: int, markdown: bool) -> str:
    return f"**{value}**" if markdown else str(value)


def _baseline_chat_verb(baseline_present: bool) -> str:
    return "update the baseline" if baseline_present else "save the baseline"


def build_outcome_summary(report: dict, manual_items: List[dict], markdown: bool = False) -> dict:
    summary = report.get("summary", {})
    auto_count = int(summary.get("auto_fixable_count", 0) or 0)
    input_count = int(summary.get("needs_input_count", 0) or 0)
    manual_review_count = int(summary.get("manual_review_count", 0) or 0)
    guided_check_count = len(manual_items)
    active_finding_count = int(summary.get("scanner_detected_issue_count", 0) or 0)
    baseline_present = bool(report.get("baseline_comparison", {}).get("baseline_present"))
    count = lambda value: _format_outcome_count(value, markdown)

    if active_finding_count > 0:
        body = (
            f"Found {count(active_finding_count)} active findings: "
            f"{count(auto_count)} safe to fix now, "
            f"{count(input_count)} need your decision"
        )
        if manual_review_count > 0:
            body += f", {count(manual_review_count)} to review manually"
        body += "."
        if guided_check_count > 0:
            body += f" Also generated {count(guided_check_count)} guided checks for this target."
    elif guided_check_count == 0 and not baseline_present:
        body = 'No active findings. Say "save the baseline" to lock this clean run in as the regression reference.'
    elif guided_check_count == 0 and baseline_present:
        body = 'No active findings. Say "update the baseline" to refresh the regression reference with this clean run.'
    elif not baseline_present:
        body = (
            f'No active findings. Generated {count(guided_check_count)} guided checks for this target '
            '— say "give me the checklist" to walk through them, or "save the baseline" to lock this clean run in.'
        )
    else:
        body = (
            f'No active findings. Generated {count(guided_check_count)} guided checks for this target '
            '— say "give me the checklist" to walk through them, or "update the baseline" to refresh it.'
        )

    return {
        "active_finding_count": active_finding_count,
        "auto_count": auto_count,
        "input_count": input_count,
        "manual_review_count": manual_review_count,
        "guided_check_count": guided_check_count,
        "baseline_present": baseline_present,
        "baseline_verb": _baseline_chat_verb(baseline_present),
        "outcome_body": body,
    }


def _test_it_yourself_variant(manual_review_count: int, guided_check_count: int) -> Optional[str]:
    if manual_review_count > 0 and guided_check_count > 0:
        return (
            f'say "give me the checklist" — covers {manual_review_count} scanner-flagged findings to verify '
            f'and {guided_check_count} guided checks. Or say "show me the manual findings" for just the '
            "scanner-flagged items."
        )
    if manual_review_count > 0:
        return (
            f'say "show me the manual findings" — {manual_review_count} item'
            f'{"s" if manual_review_count != 1 else ""} the scanner flagged but a human must verify.'
        )
    if guided_check_count > 0:
        return f'say "give me the checklist" — {guided_check_count} guided checks for this target.'
    return None


def _next_step_lines(outcome_summary: dict) -> List[str]:
    lines = ["## What to do next"]
    active_finding_count = int(outcome_summary["active_finding_count"])
    auto_count = int(outcome_summary["auto_count"])
    input_count = int(outcome_summary["input_count"])
    manual_review_count = int(outcome_summary["manual_review_count"])
    guided_check_count = int(outcome_summary["guided_check_count"])
    baseline_present = bool(outcome_summary["baseline_present"])

    if auto_count > 0:
        lines.append(
            f'- **Safe to fix now ({auto_count}):** say "apply the safe fixes" and the agent will patch them.'
        )
    if input_count > 0:
        lines.append(
            f'- **Needs your decision ({input_count}):** say "walk me through the decisions" to answer them one at a time.'
        )

    test_it_yourself = _test_it_yourself_variant(manual_review_count, guided_check_count)
    if test_it_yourself:
        lines.append(f"- **Test it yourself:** {test_it_yourself}")

    if active_finding_count == 0:
        lines.append(
            f'- **Baseline:** say "{_baseline_chat_verb(baseline_present)}" so this clean run becomes the regression reference.'
        )
    elif baseline_present:
        lines.append(
            '- **Baseline:** say "save the baseline" to make this run the new reference, '
            'or "update the baseline" to refresh the existing one.'
        )
    else:
        lines.append('- **Baseline:** say "save the baseline" to make this run the new reference.')

    lines.append("")
    return lines


def build_markdown_report(
    report: dict,
    message_lookup: Dict[str, str],
    manual_items: List[dict],
    step_failures: List[dict],
    render_context: Optional[dict] = None,
) -> str:
    findings = report["findings"]
    active_findings = [f for f in findings if f["status"] == "open" and f["triage_group"] != "not_checked"]
    groups = defaultdict(list)
    for finding in active_findings:
        groups[finding["triage_group"]].append(finding)

    waived_findings = [f for f in findings if f["status"] == "waived"]
    historical_findings = [f for f in findings if f["status"] in {"fixed", "resolved", "stale"}]
    not_checked_findings = [f for f in findings if f["triage_group"] == "not_checked"]

    auto_issues = groups["autofix"]
    input_issues = groups["needs_input"]
    manual_issues = groups["manual_review"]
    outcome_summary = build_outcome_summary(report, manual_items, markdown=True)

    generated_at = _parse_iso(report["generated_at"])
    report_date = generated_at.date().isoformat() if generated_at else date.today().isoformat()

    lines = []
    lines.append("# Accessibility Audit Report\n")
    lines.append(f"**Date**: {report_date}")
    lines.append("")
    lines.append(outcome_summary["outcome_body"])
    lines.append("")
    lines.extend(_snapshot_lines(report, render_context))
    lines.extend(_next_step_lines(outcome_summary))
    status_counts = report["summary"].get("status_counts", {})
    if status_counts.get("waived") or status_counts.get("fixed") or status_counts.get("resolved") or status_counts.get("stale"):
        status_parts = [
            f"{status} {count}"
            for status, count in status_counts.items()
            if status != "open" and count
        ]
        lines.append(f"Tracked statuses: {', '.join(status_parts)}.")
    baseline_comparison = report.get("baseline_comparison", {})
    if baseline_comparison.get("baseline_present"):
        baseline_parts = [
            f"{name} {count}"
            for name, count in baseline_comparison.get("summary", {}).items()
            if count
        ]
        if baseline_parts:
            lines.append(f"Regression summary: {', '.join(baseline_parts)}.")
    lines.append("")
    lines.append("---\n")

    if auto_issues:
        lines.append(f"## Safe to fix now ({len(auto_issues)})")
        lines.append("")
        lines.append('_The agent can apply these without further input. Say "apply the safe fixes" to proceed, or list which to skip._')
        lines.append("")
        for index, finding in enumerate(auto_issues, start=1):
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_markdown_location(finding)}")
            if _comparison_value(finding):
                lines.append(f"**Baseline**: {_comparison_value(finding)}")
            if _blast_radius_value(finding):
                lines.append(f"**Blast radius**: {_blast_radius_value(finding)}")
            lines.append(f"**Issue**: {_finding_message(finding, message_lookup)}")
            lines.append("**Fix**:")
            lines.append(finding["proposed_fix"]["diff"] or "*(No automatic fix template available)*")
            lines.append("")
        lines.append("---\n")

    if input_issues:
        lines.append(f"## Needs your decision ({len(input_issues)})")
        lines.append("")
        lines.append('_Each item asks one question. Say "walk me through the decisions" and the agent will go one at a time._')
        lines.append("")
        for index, finding in enumerate(input_issues, start=1):
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_markdown_location(finding)}")
            if _comparison_value(finding):
                lines.append(f"**Baseline**: {_comparison_value(finding)}")
            if _blast_radius_value(finding):
                lines.append(f"**Blast radius**: {_blast_radius_value(finding)}")
            lines.append(f"**Issue**: {_finding_message(finding, message_lookup)}")
            lines.append(f"**Decision needed**: {finding['decision_required']['question']}")
            current_code = finding["evidence"]["snippet"] or finding["evidence"]["dom_snippet"]
            if current_code:
                lines.append("**Current code**:")
                lines.append(f"```\n{current_code}\n```")
            lines.append("")
        lines.append("---\n")

    if manual_issues or manual_items:
        lines.append("## Test it yourself")
        lines.append("")
        lines.append("_These require a human in the browser or with assistive tech — the things automated scanners can't reliably check._")
        lines.append("")
    if manual_issues:
        lines.append(f"### Manual findings ({len(manual_issues)})")
        lines.append("")
        for index, finding in enumerate(manual_issues, start=1):
            lines.append(f"#### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_markdown_location(finding)}")
            if _comparison_value(finding):
                lines.append(f"**Baseline**: {_comparison_value(finding)}")
            if _blast_radius_value(finding):
                lines.append(f"**Blast radius**: {_blast_radius_value(finding)}")
            lines.append(f"**Issue**: {_finding_message(finding, message_lookup)}")
            lines.append("")
    if manual_items:
        lines.append(f"### Guided checklist ({len(manual_items)})")
        lines.append("")
        lines.extend(_render_guided_checklist(manual_items, step_failures))
    if manual_issues or manual_items:
        lines.append("---\n")

    if waived_findings:
        lines.append(f"## Waived (skipped on purpose) ({len(waived_findings)})")
        lines.append("")
        for index, finding in enumerate(waived_findings, start=1):
            waiver = finding["waiver"] or {}
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_markdown_location(finding)}")
            if _comparison_value(finding):
                lines.append(f"**Baseline**: {_comparison_value(finding)}")
            if _blast_radius_value(finding):
                lines.append(f"**Blast radius**: {_blast_radius_value(finding)}")
            lines.append(f"**Reason**: {waiver.get('reason', '')}")
            lines.append(f"**Approved by**: {waiver.get('approved_by', '')}")
            lines.append(f"**Expires**: {waiver.get('expires_at', '')}")
            lines.append("")
        lines.append("---\n")

    if historical_findings:
        lines.append(f"## Resolved & tracked ({len(historical_findings)})")
        lines.append("")
        lines.append("These findings were carried from status records and are kept for tracking, not active remediation:")
        lines.append("")
        for index, finding in enumerate(historical_findings, start=1):
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_markdown_location(finding)}")
            lines.append(f"**Status**: {finding['status']}")
            if _comparison_value(finding):
                lines.append(f"**Baseline**: {_comparison_value(finding)}")
            if _blast_radius_value(finding):
                lines.append(f"**Blast radius**: {_blast_radius_value(finding)}")
            lines.append(f"**Reason**: {finding['group_reason']}")
            lines.append("")
        lines.append("---\n")

    lines.append("## Not checked by this audit")
    lines.append("")
    lines.append("These WCAG criteria are outside what the scanners can evaluate. "
                 "The audit above is incomplete without addressing these separately:")
    lines.extend(_render_not_checked_lines(not_checked_findings))

    return "\n".join(lines)


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
    scope_metadata = build_scope_metadata(report, changed_files)
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
        scope_metadata=scope_metadata,
        ci_mode=True,
    )
    if args.summary_output:
        Path(args.summary_output).write_text(summary + "\n", encoding="utf-8")
    else:
        print(summary)
    return 1 if args.ci and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
