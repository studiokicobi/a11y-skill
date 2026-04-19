#!/usr/bin/env python3
"""
triage.py — consume static + runtime scanner JSON and emit triaged reports.

Merges issues from both scanners, deduplicates where rules overlap, applies the
triage rules from references/triage-rules.md, validates normalized findings
against the current schema contract, and writes markdown and/or JSON reports.

Usage:
    python3 triage.py --static results-static.json [--runtime results-runtime.json] \
        [--output report.md] [--json-output report.json] [--status-file status.json]
"""

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SCANNER_VERSION = "2.2.0"
STANDARD = "WCAG 2.2 Level AA"
DEFAULT_CONFIDENCE = "medium"
REPORT_GROUPS = ("autofix", "needs_input", "manual_review", "not_checked")
STATUS_VALUES = {"open", "waived", "resolved", "fixed", "stale"}
FIX_SAFETY_VALUES = {"safe", "guarded", "input-required", "manual-only"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
SEVERITY_VALUES = {"minor", "moderate", "serious", "critical", "n/a"}
SCANNER_VALUES = {"static", "runtime", "stateful", "manual-template", "token"}
COVERAGE_PATH = Path(__file__).resolve().parent.parent / "references" / "wcag_coverage.md"


# Rule → triage group mapping. For anything not in this map, we fall back to
# the issue's triage_hint from the scanner.
RULE_TO_GROUP = {
    # Auto-fixable
    "clickable-div": "auto",
    "redundant-role": "auto",
    "target-blank-no-noopener": "auto",
    "html-missing-lang": "auto",
    "input-placeholder-as-label": "auto",
    "tailwind-low-contrast": "auto",
    "css-low-contrast": "auto",
    "outline-none": "auto",
    "aria-hidden-focusable": "auto",
    "duplicate-id": "auto",

    # Needs input
    "img-missing-alt": "input",
    "input-missing-label": "input",
    "positive-tabindex": "input",
    "media-autoplay": "input",
    "heading-order": "input",
}


RULE_TO_SEVERITY = {
    "img-missing-alt": "serious",
    "clickable-div": "serious",
    "redundant-role": "minor",
    "target-blank-no-noopener": "moderate",
    "html-missing-lang": "moderate",
    "input-missing-label": "serious",
    "input-placeholder-as-label": "serious",
    "tailwind-low-contrast": "moderate",
    "css-low-contrast": "moderate",
    "outline-none": "serious",
    "aria-hidden-focusable": "serious",
    "media-autoplay": "moderate",
    "positive-tabindex": "moderate",
    "duplicate-id": "moderate",
    "color-contrast": "serious",
    "heading-order": "moderate",
}


RULE_TO_CONFIDENCE = {
    "img-missing-alt": "high",
    "clickable-div": "high",
    "redundant-role": "high",
    "target-blank-no-noopener": "high",
    "html-missing-lang": "high",
    "input-missing-label": "high",
    "input-placeholder-as-label": "high",
    "tailwind-low-contrast": "medium",
    "css-low-contrast": "medium",
    "outline-none": "high",
    "aria-hidden-focusable": "high",
    "media-autoplay": "medium",
    "positive-tabindex": "high",
    "duplicate-id": "medium",
    "color-contrast": "high",
    "heading-order": "medium",
}


def _get_tailwind_replacement(cls: str) -> str:
    mapping = {
        "text-gray-300": "text-gray-600",
        "text-gray-400": "text-gray-600",
        "text-slate-300": "text-slate-600",
        "text-slate-400": "text-slate-600",
        "text-zinc-300": "text-zinc-600",
        "text-zinc-400": "text-zinc-600",
        "text-neutral-300": "text-neutral-600",
        "text-neutral-400": "text-neutral-600",
        "text-stone-300": "text-stone-600",
        "text-stone-400": "text-stone-600",
        "text-red-300": "text-red-700",
        "text-red-400": "text-red-700",
        "text-blue-300": "text-blue-700",
        "text-blue-400": "text-blue-700",
        "text-green-300": "text-green-700",
        "text-green-400": "text-green-700",
        "text-yellow-300": "text-yellow-800",
        "text-yellow-400": "text-yellow-800",
        "text-orange-300": "text-orange-700",
        "text-orange-400": "text-orange-700",
    }
    return mapping.get(cls, cls + " (no automatic replacement — pick manually)")


def _get_color_replacement(color: str) -> str:
    mapping = {
        "#aaa": "#767676", "#aaaaaa": "#767676",
        "#bbb": "#767676", "#bbbbbb": "#767676",
        "#ccc": "#707070", "#cccccc": "#707070",
        "#999": "#767676", "#999999": "#767676",
        "#888": "#767676", "#888888": "#767676",
    }
    return mapping.get(color.lower(), color)


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "field"


def _suggest_input_id(issue: dict, fix_data: dict) -> str:
    base = fix_data.get("name") or fix_data.get("placeholder") or "field"
    return f"{_slugify(base)}-{issue.get('line', 0)}"


def diff(before: str, after: str) -> str:
    before_lines = before.splitlines() or [""]
    after_lines = after.splitlines() or [""]
    lines = ["```diff"]
    for line in before_lines:
        lines.append(f"- {line}")
    for line in after_lines:
        lines.append(f"+ {line}")
    lines.append("```")
    return "\n".join(lines)


def render_fix(issue: dict) -> Optional[str]:
    rule_id = issue["rule_id"]
    snippet = issue.get("snippet", "").strip()
    fix_data = issue.get("fix_data", {})
    framework = issue.get("framework", "html")

    if rule_id == "clickable-div":
        element = fix_data.get("element", "div")
        before = snippet
        after = snippet.replace(f"<{element}", "<button type=\"button\"", 1)
        after = after.replace(f"</{element}>", "</button>")
        return diff(before, after)

    if rule_id == "redundant-role":
        role = fix_data.get("role", "")
        before = snippet
        after = snippet
        for pattern in (f' role="{role}"', f" role='{role}'"):
            after = after.replace(pattern, "")
        return diff(before, after)

    if rule_id == "target-blank-no-noopener":
        before = snippet
        if "rel=" in snippet:
            match = re.search(r'rel\s*=\s*([\'"])([^\'"]*)([\'"])', snippet, re.IGNORECASE)
            if not match:
                return None
            quote = match.group(1)
            tokens = match.group(2).split()
            for token in ("noopener", "noreferrer"):
                if token not in tokens:
                    tokens.append(token)
            merged = " ".join(tokens)
            after = snippet[:match.start()] + f'rel={quote}{merged}{quote}' + snippet[match.end():]
            return diff(before, after)
        after = snippet.replace(
            'target="_blank"',
            'target="_blank" rel="noopener noreferrer"',
            1,
        )
        after = after.replace(
            "target='_blank'",
            "target='_blank' rel='noopener noreferrer'",
            1,
        )
        return diff(before, after)

    if rule_id == "html-missing-lang":
        before = snippet
        after = snippet.replace("<html", '<html lang="en"', 1)
        return (
            diff(before, after)
            + "\n<!-- note: verify 'en' is correct; check package.json or existing content -->"
        )

    if rule_id == "input-placeholder-as-label":
        placeholder = fix_data.get("placeholder", "")
        input_id = _suggest_input_id(issue, fix_data)
        before = snippet
        after = (
            f'<label htmlFor="{input_id}">{placeholder}</label>\n'
            + snippet.replace(
                f'placeholder="{placeholder}"',
                f'id="{input_id}" placeholder="{placeholder}"',
                1,
            )
        )
        if framework in {"vue", "angular", "html", "svelte"}:
            after = after.replace("htmlFor", "for")
        return diff(before, after)

    if rule_id == "tailwind-low-contrast":
        cls = fix_data.get("class", "")
        replacement = _get_tailwind_replacement(cls)
        return diff(snippet, snippet.replace(cls, replacement))

    if rule_id == "css-low-contrast":
        color = fix_data.get("color", "")
        replacement = _get_color_replacement(color)
        return diff(snippet, snippet.replace(color, replacement))

    if rule_id == "outline-none":
        return (
            "```css\n"
            "/* Add alongside the existing `outline: none` rule: */\n"
            ":focus-visible {\n"
            "  outline: 2px solid currentColor;\n"
            "  outline-offset: 2px;\n"
            "}\n"
            "```\n"
            "<!-- note: use your brand accent color instead of currentColor if appropriate -->"
        )

    if rule_id == "aria-hidden-focusable":
        before = snippet
        after = snippet.replace('aria-hidden="true"', "").replace("aria-hidden='true'", "")
        after = " ".join(after.split())
        return diff(before, after)

    return None


def humanize_rule(rule_id: str) -> str:
    titles = {
        "img-missing-alt": "Image missing alt attribute",
        "clickable-div": "Non-interactive element with click handler",
        "redundant-role": "Redundant ARIA role",
        "target-blank-no-noopener": 'target="_blank" without rel="noopener"',
        "html-missing-lang": "<html> missing lang attribute",
        "input-missing-label": "Input missing label",
        "input-placeholder-as-label": "Placeholder used as only label",
        "tailwind-low-contrast": "Low-contrast Tailwind class",
        "css-low-contrast": "Low-contrast color in CSS",
        "outline-none": "Focus indicator removed",
        "aria-hidden-focusable": "aria-hidden on focusable element",
        "media-autoplay": "Autoplay on media element",
        "positive-tabindex": "Positive tabindex disrupts tab order",
        "duplicate-id": "Duplicate id attribute",
        "color-contrast": "Color contrast failure (runtime)",
        "heading-order": "Heading order skip",
    }
    return titles.get(rule_id, rule_id.replace("-", " ").capitalize())


def decision_prompt(issue: dict) -> str:
    prompts = {
        "img-missing-alt": 'What does this image convey? (For decorative images, we\'ll use alt="".)',
        "input-missing-label": "What should this input be labeled?",
        "positive-tabindex": "Is this tab order deliberate? If not, we'll remove the positive tabindex.",
        "media-autoplay": "Keep autoplay with pause controls, or remove autoplay entirely?",
        "color-contrast": "Pick an accessible color that aligns with your brand — we'll suggest 2–3 options if you want.",
        "heading-order": "Should the out-of-order heading be downgraded/upgraded to match the sequence, or should we restructure the page hierarchy?",
    }
    return prompts.get(issue["rule_id"], "Review and confirm the proposed fix below.")


def _signature(snippet: str) -> str:
    if not snippet:
        return ""
    match = re.search(r"<(\w+)\b[^>]*>", snippet)
    if not match:
        return snippet[:60].lower()
    tag = match.group(1).lower()
    attrs = snippet[match.start():match.end()]
    for attr in ("id", "class", "src", "href", "name"):
        val_match = re.search(rf'\b{attr}\s*=\s*["\']([^"\']+)', attrs, re.IGNORECASE)
        if val_match:
            return f"{tag}:{attr}:{val_match.group(1)}".lower()
    return tag


def _dedup_key(issue: dict) -> tuple:
    scanner = _infer_scanner(issue)
    selector = issue.get("fix_data", {}).get("target", "")
    snippet_norm = re.sub(r"\s+", " ", issue.get("snippet", "")).strip().lower()
    return (
        scanner,
        issue["rule_id"],
        issue.get("file", ""),
        issue.get("line", 0),
        issue.get("journey_step_id", "") or issue.get("fix_data", {}).get("journey_step_id", ""),
        selector,
        snippet_norm[:120],
    )


def deduplicate(issues: List[dict]) -> List[dict]:
    seen = {}
    for issue in issues:
        key = _dedup_key(issue)
        if key in seen:
            if len(issue.get("snippet", "")) > len(seen[key].get("snippet", "")):
                seen[key] = issue
        else:
            seen[key] = issue
    deduped = list(seen.values())

    by_rule = defaultdict(list)
    for issue in deduped:
        by_rule[issue["rule_id"]].append(issue)

    merged = []
    consumed = set()
    for rule_id, rule_issues in by_rule.items():
        static_issues = [i for i in rule_issues if _infer_scanner(i) == "static"]
        runtime_issues = [i for i in rule_issues if _infer_scanner(i) == "runtime"]
        stateful_issues = [i for i in rule_issues if _infer_scanner(i) == "stateful"]
        other_issues = [
            i for i in rule_issues
            if _infer_scanner(i) not in {"static", "runtime", "stateful"}
        ]

        for static_issue in static_issues:
            static_sig = _signature(static_issue.get("snippet", ""))
            for runtime_issue in runtime_issues:
                runtime_sig = _signature(runtime_issue.get("snippet", ""))
                if runtime_sig and static_sig and (runtime_sig in static_sig or static_sig in runtime_sig):
                    static_issue.setdefault("fix_data", {})["confirmed_by_runtime"] = True
                    consumed.add(id(runtime_issue))
                    break
            merged.append(static_issue)

        for runtime_issue in runtime_issues:
            if id(runtime_issue) not in consumed:
                merged.append(runtime_issue)

        merged.extend(stateful_issues)
        merged.extend(other_issues)

    return merged


def classify(issue: dict) -> str:
    if issue["rule_id"] in RULE_TO_GROUP:
        return RULE_TO_GROUP[issue["rule_id"]]
    return issue.get("triage_hint", "input")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _output_dir(markdown_output: Optional[str], json_output: Optional[str]) -> Path:
    for path_str in (json_output, markdown_output):
        if path_str:
            return Path(path_str).resolve().parent
    return Path.cwd()


def _relative_artifact_path(path_str: str, output_dir: Path) -> str:
    if not path_str:
        return ""
    candidate = Path(path_str)
    if not candidate.is_absolute():
        return path_str
    return os.path.relpath(candidate.resolve(), output_dir.resolve())


def _infer_scanner(issue: dict) -> str:
    scanner = issue.get("scanner", "")
    if scanner in SCANNER_VALUES:
        return scanner
    if (
        issue.get("framework") == "stateful"
        or issue.get("journey_step_id")
        or issue.get("fix_data", {}).get("journey_step_id")
    ):
        return "stateful"
    if issue.get("framework") == "runtime" or issue.get("origin_rule_id") or issue.get("fix_data", {}).get("axe_rule"):
        return "runtime"
    return "static"


def _infer_severity(issue: dict) -> str:
    impact = issue.get("fix_data", {}).get("impact", "").lower()
    if impact in SEVERITY_VALUES - {"n/a"}:
        return impact
    return RULE_TO_SEVERITY.get(issue["rule_id"], "n/a")


def _infer_confidence(issue: dict) -> str:
    if issue.get("fix_data", {}).get("result_type") == "incomplete":
        return "low"
    return RULE_TO_CONFIDENCE.get(issue["rule_id"], DEFAULT_CONFIDENCE)


def _fix_safety_for_group(group: str) -> str:
    mapping = {
        "autofix": "safe",
        "needs_input": "input-required",
        "manual_review": "manual-only",
        "not_checked": "manual-only",
    }
    return mapping[group]


def _group_reason(issue: dict, triage_group: str, status: str = "open") -> str:
    if status == "waived":
        return "Finding matched an active waiver record and was moved out of the active remediation groups."
    if status in {"resolved", "fixed", "stale"}:
        return f"Finding status is {status}; it is tracked for reporting but not surfaced in active remediation groups."
    if triage_group == "autofix":
        return "Rule is classified as safe to patch automatically for this evidence source."
    if triage_group == "needs_input":
        return "Finding requires human input, content intent, or scanner uncertainty before remediation."
    if triage_group == "manual_review":
        return "Finding requires manual verification or assistive-technology testing."
    return "Criterion is declared outside this run's checked coverage and is surfaced in the not-checked section."


def _decision_required(issue: dict, triage_group: str) -> dict:
    if triage_group != "needs_input":
        return {"question": "", "options": []}
    return {"question": decision_prompt(issue), "options": []}


def _proposed_fix(issue: dict, triage_group: str) -> dict:
    if triage_group != "autofix":
        return {"kind": "none", "diff": "", "notes": ""}
    fix = render_fix(issue)
    if fix:
        return {"kind": "diff", "diff": fix, "notes": ""}
    return {"kind": "none", "diff": "", "notes": "No automatic fix template is available yet."}


def _origin_rule_id(issue: dict) -> Optional[str]:
    return issue.get("origin_rule_id") or issue.get("fix_data", {}).get("axe_rule")


def _confirmed_by(issue: dict, scanner: str) -> List[str]:
    confirmed = {scanner}
    if issue.get("fix_data", {}).get("confirmed_by_runtime"):
        confirmed.add("runtime")
    if issue.get("fix_data", {}).get("confirmed_by_stateful"):
        confirmed.add("stateful")
    return sorted(confirmed)


def _fingerprint(issue: dict, scanner: str) -> str:
    selector = issue.get("fix_data", {}).get("target", "")
    snippet_sig = _signature(issue.get("snippet", ""))
    step_id = issue.get("journey_step_id", "") or issue.get("fix_data", {}).get("journey_step_id", "")
    if scanner == "stateful":
        return "|".join([
            issue["rule_id"],
            str(issue.get("file", "")),
            selector or snippet_sig,
            step_id,
        ])
    if scanner == "runtime":
        return "|".join([
            issue["rule_id"],
            str(issue.get("file", "")),
            selector or snippet_sig,
        ])
    return "|".join([
        issue["rule_id"],
        str(issue.get("file", "")),
        str(issue.get("line", 0)),
        snippet_sig,
    ])


def _finding_id(fingerprint: str) -> str:
    return hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]


def _normalize_location(issue: dict) -> dict:
    scanner = _infer_scanner(issue)
    if scanner in {"runtime", "stateful"}:
        return {
            "file": "",
            "line": 0,
            "column": 0,
            "url": issue.get("file", ""),
            "selector": issue.get("fix_data", {}).get("target", ""),
            "journey_step_id": issue.get("journey_step_id", "") or issue.get("fix_data", {}).get("journey_step_id", ""),
        }
    return {
        "file": issue.get("file", ""),
        "line": int(issue.get("line", 0) or 0),
        "column": int(issue.get("col", 0) or 0),
        "url": "",
        "selector": "",
        "journey_step_id": "",
    }


def _normalize_evidence(issue: dict, output_dir: Path) -> dict:
    scanner = _infer_scanner(issue)
    screenshot = issue.get("fix_data", {}).get("screenshot", "")
    if scanner in {"runtime", "stateful"}:
        return {
            "snippet": "",
            "dom_snippet": issue.get("snippet", ""),
            "screenshot": _relative_artifact_path(screenshot, output_dir),
            "axe_help_url": issue.get("fix_data", {}).get("help_url", ""),
        }
    return {
        "snippet": issue.get("snippet", ""),
        "dom_snippet": "",
        "screenshot": _relative_artifact_path(screenshot, output_dir),
        "axe_help_url": "",
    }


def normalize_finding(issue: dict, detected_at: str, output_dir: Path) -> dict:
    scanner = _infer_scanner(issue)
    triage_group = {
        "auto": "autofix",
        "input": "needs_input",
        "manual": "manual_review",
    }.get(classify(issue), "needs_input")
    fingerprint = _fingerprint(issue, scanner)
    normalized = {
        "id": _finding_id(fingerprint),
        "rule_id": issue["rule_id"],
        "title": humanize_rule(issue["rule_id"]),
        "wcag": [issue["wcag"]] if issue.get("wcag") else [],
        "severity": _infer_severity(issue),
        "scanner": scanner,
        "scanner_version": SCANNER_VERSION,
        "detected_at": detected_at,
        "triage_group": triage_group,
        "fix_safety": _fix_safety_for_group(triage_group),
        "confidence": _infer_confidence(issue),
        "status": "open",
        "waiver": None,
        "group_reason": _group_reason(issue, triage_group),
        "location": _normalize_location(issue),
        "mapping": {
            "source_file": "",
            "source_line": 0,
            "confidence": "low",
            "explanation": "",
        },
        "evidence": _normalize_evidence(issue, output_dir),
        "decision_required": _decision_required(issue, triage_group),
        "proposed_fix": _proposed_fix(issue, triage_group),
        "fingerprint": fingerprint,
        "confirmed_by": _confirmed_by(issue, scanner),
    }
    origin_rule_id = _origin_rule_id(issue)
    if origin_rule_id:
        normalized["origin_rule_id"] = origin_rule_id
    return normalized


def load_status_records(path_str: Optional[str]) -> List[dict]:
    if not path_str:
        return []
    data = json.loads(Path(path_str).read_text())
    records = list(data.get("records", []))
    for waiver in data.get("waivers", []):
        records.append({
            "status": "waived",
            "match": waiver.get("match", {}),
            "fingerprint": waiver.get("fingerprint", ""),
            "waiver": {
                "reason": waiver.get("reason", ""),
                "approved_by": waiver.get("approved_by", ""),
                "expires_at": waiver.get("expires_at", ""),
            },
        })
    return records


def _historical_finding_from_record(record: dict, detected_at: str) -> Optional[dict]:
    finding = record.get("finding")
    if not isinstance(finding, dict):
        return None

    finding = copy.deepcopy(finding)
    finding.setdefault("scanner_version", SCANNER_VERSION)
    finding.setdefault("detected_at", detected_at)
    finding.setdefault("waiver", None)

    status = record.get("status", finding.get("status", "open"))
    if status not in STATUS_VALUES:
        return None

    finding["status"] = status
    if status == "waived":
        waiver = record.get("waiver") or finding.get("waiver") or {}
        finding["waiver"] = {
            "reason": waiver.get("reason", ""),
            "approved_by": waiver.get("approved_by", ""),
            "expires_at": waiver.get("expires_at", ""),
        }
    else:
        finding["waiver"] = None

    finding["group_reason"] = _group_reason(
        finding,
        finding.get("triage_group", "manual_review"),
        status,
    )
    return finding


def _status_record_matches(record: dict, finding: dict) -> bool:
    fingerprint = record.get("fingerprint", "")
    if fingerprint:
        return fingerprint == finding["fingerprint"]

    match = record.get("match", {})
    if not match:
        return False

    scalar_fields = ("rule_id", "origin_rule_id")
    for field in scalar_fields:
        if match.get(field) and finding.get(field) != match[field]:
            return False

    location = finding["location"]
    location_checks = {
        "file": location.get("file", ""),
        "line": location.get("line", 0),
        "url": location.get("url", ""),
        "selector": location.get("selector", ""),
    }
    for field, actual in location_checks.items():
        if field in match and match[field] != actual:
            return False
    return True


def apply_status_records(findings: List[dict], records: List[dict], detected_at: str) -> List[dict]:
    detected_at_dt = _parse_iso(detected_at)
    for finding in findings:
        for record in records:
            if not _status_record_matches(record, finding):
                continue

            status = record.get("status", "open")
            if status not in STATUS_VALUES:
                continue

            if status == "waived":
                waiver = record.get("waiver", {})
                expires_at = waiver.get("expires_at", "")
                expires_dt = _parse_iso(expires_at)
                if expires_dt and detected_at_dt and expires_dt < detected_at_dt:
                    finding["status"] = "open"
                    finding["waiver"] = None
                    finding["group_reason"] = _group_reason(finding, finding["triage_group"], "open")
                    continue
                finding["status"] = "waived"
                finding["waiver"] = {
                    "reason": waiver.get("reason", ""),
                    "approved_by": waiver.get("approved_by", ""),
                    "expires_at": expires_at,
                }
                finding["group_reason"] = _group_reason(finding, finding["triage_group"], "waived")
                continue

            finding["status"] = status
            finding["waiver"] = None
            finding["group_reason"] = _group_reason(finding, finding["triage_group"], status)

    existing_fingerprints = {finding["fingerprint"] for finding in findings}
    historical = []
    for record in records:
        finding = _historical_finding_from_record(record, detected_at)
        if not finding:
            continue
        fingerprint = finding.get("fingerprint", "")
        if not fingerprint or fingerprint in existing_fingerprints:
            continue
        existing_fingerprints.add(fingerprint)
        historical.append(finding)

    findings.extend(historical)
    return findings


def load_wcag_coverage() -> List[dict]:
    if not COVERAGE_PATH.exists():
        return []

    rows = []
    for raw_line in COVERAGE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0].lower() == "criterion" or set(cells[0]) == {"-"}:
            continue
        row = {
            "criterion": cells[0],
            "title": cells[1],
            "coverage": cells[2],
        }
        if len(cells) > 3:
            row["notes"] = cells[3]
        rows.append(row)
    return rows


def build_not_checked_findings(detected_at: str) -> List[dict]:
    findings = []
    for row in load_wcag_coverage():
        if row["coverage"] != "out-of-scope":
            continue
        criterion = row["criterion"]
        fingerprint = f"not-checked|{criterion}"
        findings.append({
            "id": _finding_id(fingerprint),
            "rule_id": f"not-checked-{criterion.replace('.', '-')}",
            "title": row["title"],
            "wcag": [criterion],
            "severity": "n/a",
            "scanner": "manual-template",
            "scanner_version": SCANNER_VERSION,
            "detected_at": detected_at,
            "triage_group": "not_checked",
            "fix_safety": "manual-only",
            "confidence": "high",
            "status": "open",
            "waiver": None,
            "group_reason": "Criterion is declared out-of-scope in references/wcag_coverage.md.",
            "location": {
                "file": "",
                "line": 0,
                "column": 0,
                "url": "",
                "selector": "",
                "journey_step_id": "",
            },
            "mapping": {
                "source_file": "",
                "source_line": 0,
                "confidence": "low",
                "explanation": "",
            },
            "evidence": {
                "snippet": "",
                "dom_snippet": "",
                "screenshot": "",
                "axe_help_url": "",
            },
            "decision_required": {"question": "", "options": []},
            "proposed_fix": {"kind": "none", "diff": "", "notes": row.get("notes", "")},
            "fingerprint": fingerprint,
            "confirmed_by": ["manual-template"],
        })
    return findings


def _sort_findings(findings: Iterable[dict]) -> List[dict]:
    order = {group: index for index, group in enumerate(REPORT_GROUPS)}

    def key(finding: dict) -> tuple:
        location = finding["location"]
        return (
            finding["status"] != "open",
            order.get(finding["triage_group"], 99),
            finding["status"],
            finding["wcag"][0] if finding["wcag"] else "",
            location.get("file", ""),
            location.get("url", ""),
            location.get("line", 0),
            finding["rule_id"],
        )

    return sorted(findings, key=key)


def validate_finding_schema(finding: dict) -> None:
    required_fields = {
        "id": str,
        "rule_id": str,
        "title": str,
        "wcag": list,
        "severity": str,
        "scanner": str,
        "scanner_version": str,
        "detected_at": str,
        "triage_group": str,
        "fix_safety": str,
        "confidence": str,
        "status": str,
        "location": dict,
        "mapping": dict,
        "evidence": dict,
        "decision_required": dict,
        "proposed_fix": dict,
        "fingerprint": str,
        "confirmed_by": list,
        "group_reason": str,
    }

    for field, field_type in required_fields.items():
        if field not in finding:
            raise ValueError(f"Missing required field: {field}")
        if not isinstance(finding[field], field_type):
            raise ValueError(f"Field {field} has wrong type: expected {field_type.__name__}")

    if finding["severity"] not in SEVERITY_VALUES:
        raise ValueError(f"Invalid severity: {finding['severity']}")
    if finding["scanner"] not in SCANNER_VALUES:
        raise ValueError(f"Invalid scanner: {finding['scanner']}")
    if finding["triage_group"] not in REPORT_GROUPS:
        raise ValueError(f"Invalid triage group: {finding['triage_group']}")
    if finding["fix_safety"] not in FIX_SAFETY_VALUES:
        raise ValueError(f"Invalid fix_safety: {finding['fix_safety']}")
    if finding["confidence"] not in CONFIDENCE_VALUES:
        raise ValueError(f"Invalid confidence: {finding['confidence']}")
    if finding["status"] not in STATUS_VALUES:
        raise ValueError(f"Invalid status: {finding['status']}")
    if not all(isinstance(code, str) for code in finding["wcag"]):
        raise ValueError("WCAG references must be strings")
    if not all(isinstance(source, str) for source in finding["confirmed_by"]):
        raise ValueError("confirmed_by must be an array of strings")

    screenshot = finding["evidence"].get("screenshot", "")
    if screenshot and Path(screenshot).is_absolute():
        raise ValueError("evidence.screenshot must be relative")

    waiver = finding.get("waiver")
    if finding["status"] == "waived":
        if not isinstance(waiver, dict):
            raise ValueError("waived findings must carry a waiver object")
        for field in ("reason", "approved_by", "expires_at"):
            if field not in waiver or not isinstance(waiver[field], str):
                raise ValueError(f"waiver.{field} is required for waived findings")
    elif waiver not in (None,):
        raise ValueError("non-waived findings must not emit a waiver object")


def validate_report_schema(report: dict) -> None:
    for field in ("schema_version", "generated_at", "target", "framework", "standard", "findings", "summary", "coverage_metadata"):
        if field not in report:
            raise ValueError(f"Missing report field: {field}")
    if not isinstance(report["findings"], list):
        raise ValueError("Report findings must be an array")
    for finding in report["findings"]:
        validate_finding_schema(finding)


def build_report_data(
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    output_dir: Path,
    detected_at: str,
    status_records: List[dict],
) -> dict:
    issues = []
    if static_data:
        issues.extend(static_data.get("issues", []))
    if runtime_data:
        issues.extend(runtime_data.get("issues", []))
    if stateful_data:
        issues.extend(stateful_data.get("issues", []))

    normalized_findings = [
        normalize_finding(issue, detected_at, output_dir)
        for issue in deduplicate(issues)
    ]
    normalized_findings = apply_status_records(normalized_findings, status_records, detected_at)
    normalized_findings.extend(build_not_checked_findings(detected_at))
    normalized_findings = _sort_findings(normalized_findings)

    active_findings = [
        finding for finding in normalized_findings
        if finding["status"] == "open" and finding["triage_group"] != "not_checked"
    ]
    waived_findings = [
        finding for finding in normalized_findings
        if finding["status"] == "waived"
    ]
    not_checked_findings = [
        finding for finding in normalized_findings
        if finding["triage_group"] == "not_checked"
    ]

    summary = {
        "scanner_detected_issue_count": len(active_findings),
        "auto_fixable_count": sum(1 for finding in active_findings if finding["triage_group"] == "autofix"),
        "needs_input_count": sum(1 for finding in active_findings if finding["triage_group"] == "needs_input"),
        "manual_review_count": sum(1 for finding in active_findings if finding["triage_group"] == "manual_review"),
        "waived_count": len(waived_findings),
        "not_checked_count": len(not_checked_findings),
        "by_scanner": {
            scanner: sum(1 for finding in active_findings if finding["scanner"] == scanner)
            for scanner in ("static", "runtime", "stateful", "manual-template", "token")
        },
        "by_confidence": {
            confidence: sum(1 for finding in active_findings if finding["confidence"] == confidence)
            for confidence in ("high", "medium", "low")
        },
        "status_counts": {
            status: sum(
                1
                for finding in normalized_findings
                if finding["status"] == status and finding["triage_group"] != "not_checked"
            )
            for status in ("open", "waived", "fixed", "resolved", "stale")
        },
    }

    target = (
        (static_data or runtime_data or {}).get("target")
        or ", ".join((runtime_data or {}).get("urls", []))
        or ", ".join(journey.get("start_url", "") for journey in (stateful_data or {}).get("journeys", []))
    )
    framework = (static_data or {}).get("framework") or ("stateful" if stateful_data else "unknown")

    report = {
        "schema_version": SCANNER_VERSION,
        "generated_at": detected_at,
        "target": target or "(unspecified)",
        "framework": framework,
        "standard": STANDARD,
        "summary": summary,
        "coverage_metadata": {
            "coverage_source": "references/wcag_coverage.md",
            "manual_checklist_included": True,
            "not_checked_criteria": [finding["wcag"][0] for finding in not_checked_findings],
        },
        "findings": normalized_findings,
    }
    validate_report_schema(report)
    return report


def _unique_step_ids(items: Iterable[dict], actions: Optional[Iterable[str]] = None) -> List[str]:
    allowed = set(actions or [])
    seen = []
    for item in items:
        action = item.get("action", "")
        if allowed and action not in allowed:
            continue
        step_id = item.get("journey_step_id", "")
        if step_id and step_id not in seen:
            seen.append(step_id)
    return seen


def _step_context_label(step_ids: List[str], fallback: str) -> str:
    if not step_ids:
        return fallback
    if len(step_ids) == 1:
        return f"step `{step_ids[0]}`"
    joined = ", ".join(f"`{step_id}`" for step_id in step_ids)
    return f"steps {joined}"


def _collect_manual_context(report: dict, stateful_data: Optional[dict]) -> dict:
    active_findings = [
        finding for finding in report["findings"]
        if finding["status"] == "open" and finding["triage_group"] != "not_checked"
    ]
    lower_blob = " ".join(
        " ".join([
            finding["rule_id"],
            finding["location"].get("selector", ""),
            finding["location"].get("journey_step_id", ""),
            finding["evidence"].get("snippet", ""),
            finding["evidence"].get("dom_snippet", ""),
        ]).lower()
        for finding in active_findings
    )

    transitions = list((stateful_data or {}).get("focus_transitions", []))
    step_failures = list((stateful_data or {}).get("step_failures", []))
    checkpoint_urls = {
        checkpoint.get("url", "")
        for checkpoint in (stateful_data or {}).get("checkpoints", [])
        if checkpoint.get("url")
    }

    has_forms = (
        any(
            finding["rule_id"] in {"input-missing-label", "input-placeholder-as-label", "duplicate-id"}
            for finding in active_findings
        )
        or any(event.get("action") in {"fill", "select"} for event in transitions)
        or any(token in lower_blob for token in ("<input", "<select", "<textarea", "<form"))
    )
    overlay_steps = _unique_step_ids(
        [
            event for event in transitions
            if any(token in " ".join(str(value) for value in event.values()).lower() for token in ("dialog", "modal"))
        ]
        + [
            {
                "journey_step_id": finding["location"].get("journey_step_id", ""),
                "action": "",
            }
            for finding in active_findings
            if any(token in (
                (finding["location"].get("selector", "") + " " + finding["evidence"].get("dom_snippet", "")).lower()
            ) for token in ("dialog", "modal"))
        ]
    )
    route_steps = _unique_step_ids(
        [
            event for event in transitions
            if event.get("action") == "navigate" or event.get("before_url", "") != event.get("url", "")
        ]
    )
    has_route_change = bool(route_steps) or len(checkpoint_urls) > 1
    has_dynamic_updates = bool(transitions or step_failures)

    return {
        "has_forms": has_forms,
        "has_overlay": bool(overlay_steps),
        "overlay_steps": overlay_steps,
        "route_steps": route_steps,
        "has_route_change": has_route_change,
        "has_dynamic_updates": has_dynamic_updates,
        "step_failures": step_failures,
    }


def generate_manual_review_items(report: dict, stateful_data: Optional[dict]) -> List[dict]:
    context = _collect_manual_context(report, stateful_data)
    items = [
        {
            "title": "Keyboard tab order through the audited page or flow",
            "capability": "keyboard",
            "wcag": ["2.1.1", "2.4.3"],
            "context": "Use the current page-load state and every audited interaction state.",
            "steps": [
                "Press Tab from the browser chrome into the page and keep tabbing until focus returns to the browser or the end of the flow.",
                "Repeat with Shift+Tab to verify the reverse order.",
            ],
            "expected": [
                "Every interactive element is reachable in a logical visual order.",
                "No keyboard trap appears and focus never jumps to hidden or inert UI.",
            ],
        },
        {
            "title": "Focus visibility and focus return behavior",
            "capability": "visual",
            "wcag": ["2.4.7", "2.4.11"],
            "context": "Check each interactive state reached during the audit.",
            "steps": [
                "Tab to each control, including links, buttons, fields, and custom widgets.",
                "Trigger any overlays, menus, or popovers that appear in the audited flow and then close them.",
            ],
            "expected": [
                "The active element has a visible focus indicator with sufficient contrast.",
                "When transient UI closes, focus returns to a sensible trigger or next logical control.",
            ],
        },
        {
            "title": "Heading outline and page title announcement",
            "capability": "screen reader",
            "wcag": ["1.3.1", "2.4.2", "2.4.6"],
            "context": "Inspect the current page and any post-interaction destination states.",
            "steps": [
                "Open the page or flow with a screen reader rotor/list-of-headings view.",
                "Move by heading level and confirm the document title after each destination change.",
            ],
            "expected": [
                "The title uniquely identifies the current page or state.",
                "Heading levels form a logical outline without skipped or decorative headings being announced as structure.",
            ],
        },
        {
            "title": "Zoom, reflow, and text spacing resilience",
            "capability": "browser",
            "wcag": ["1.4.10", "1.4.12"],
            "context": "Run this on the main page and any key post-interaction view.",
            "steps": [
                "Check the page at 200% zoom and then at 320px CSS width.",
                "Override text spacing to line-height 1.5, paragraph spacing 2x, letter spacing 0.12em, and word spacing 0.16em.",
            ],
            "expected": [
                "Content remains usable without horizontal scrolling for main reading content.",
                "No clipping, overlap, or lost controls appear when text spacing is increased.",
            ],
        },
        {
            "title": "Reduced motion and motion-triggered interactions",
            "capability": "visual",
            "wcag": ["2.3.*"],
            "context": "Repeat the audited journey with reduced motion enabled if the UI animates.",
            "steps": [
                "Turn on the OS or browser reduced-motion preference and replay the audited flow.",
                "Trigger any animated transitions, expanding sections, or route changes observed during the scan.",
            ],
            "expected": [
                "Non-essential motion is reduced or removed.",
                "Animations do not block task completion or hide focus movement.",
            ],
        },
        {
            "title": "Use-of-color-only communication",
            "capability": "visual",
            "wcag": ["1.4.1"],
            "context": "Check interactive controls, validation states, charts, and inline status messages.",
            "steps": [
                "Review the page in grayscale or with color filters disabled.",
                "Inspect success, error, selected, and required states across the audited flow.",
            ],
            "expected": [
                "Meaning is still clear without color perception.",
                "Status and selection are conveyed with text, iconography, or structural cues in addition to color.",
            ],
        },
    ]

    if context["has_overlay"]:
        overlay_label = _step_context_label(context["overlay_steps"], "the overlay interactions")
        items.append({
            "title": "Overlay escape, trap, and focus return",
            "capability": "keyboard",
            "wcag": ["2.1.2", "2.4.3"],
            "context": f"Replay {overlay_label}.",
            "steps": [
                f"Open the overlay reached in {overlay_label} and press Tab until you wrap through the controls.",
                "Press Escape and then reopen the overlay once more.",
            ],
            "expected": [
                "Focus stays inside the overlay while it is open, unless the pattern intentionally allows background interaction.",
                "Escape closes the overlay when appropriate, and focus returns to the trigger or next logical control.",
            ],
        })

    if context["has_forms"]:
        items.append({
            "title": "Form labels, errors, and required-state announcements",
            "capability": "screen reader",
            "wcag": ["3.3.1", "3.3.2", "4.1.2", "4.1.3"],
            "context": "Use the form states reached in the audited flow, including invalid submissions.",
            "steps": [
                "Move through each field with a screen reader and listen for label, role, value, and required state.",
                "Submit the form with missing or invalid data and listen for the first announced error.",
            ],
            "expected": [
                "Every field announces a clear programmatic label and required status.",
                "Errors are announced in text, associated to the affected field, and do not rely on color alone.",
            ],
        })

    if context["has_dynamic_updates"]:
        items.append({
            "title": "Dynamic status and validation announcements",
            "capability": "screen reader",
            "wcag": ["4.1.3"],
            "context": "Replay the audited interaction steps that update content without a full reload.",
            "steps": [
                "Trigger each audited state change that updates content, validation, or inline status.",
                "Listen for live-region, alert, or status announcements without moving virtual cursor focus manually.",
            ],
            "expected": [
                "Important updates are announced promptly.",
                "Announcements are concise and do not double-announce stale content.",
            ],
        })

    if context["has_route_change"]:
        route_label = _step_context_label(context["route_steps"], "the audited navigation steps")
        items.append({
            "title": "SPA route change announcement and focus placement",
            "capability": "screen reader",
            "wcag": ["2.4.3", "4.1.3"],
            "context": f"Replay {route_label}.",
            "steps": [
                f"Trigger the route change in {route_label}.",
                "After navigation, inspect the next focus target and listen for the destination announcement.",
            ],
            "expected": [
                "The destination announces a meaningful title, heading, or status change.",
                "Focus lands on a sensible element for the new view instead of remaining on stale UI.",
            ],
        })

    return items


def _render_manual_checklist(items: List[dict], step_failures: List[dict]) -> List[str]:
    lines = []
    if step_failures:
        lines.append("Recorded journey step failures:")
        for failure in step_failures:
            lines.append(
                f"- `{failure.get('journey_step_id', '')}` ({failure.get('action', '')}) — {failure.get('message', '')}"
            )
        lines.append("")

    lines.append("Assisted checks:")
    lines.append("")
    for index, item in enumerate(items, start=1):
        lines.append(f"### {index}. {item['title']}")
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


def _display_location(finding: dict) -> str:
    location = finding["location"]
    if location["file"]:
        return f"`{location['file']}:{location['line']}`" if location["line"] else f"`{location['file']}`"
    if location["journey_step_id"]:
        return f"`{location['url']}` after step `{location['journey_step_id']}`"
    return f"`{location['url']}`"


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


def build_markdown_report(report: dict, message_lookup: Dict[str, str], manual_items: List[dict], step_failures: List[dict]) -> str:
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

    generated_at = _parse_iso(report["generated_at"])
    report_date = generated_at.date().isoformat() if generated_at else date.today().isoformat()

    lines = []
    lines.append("# Accessibility Audit Report\n")
    lines.append(f"**Target**: {report['target']}")
    lines.append(f"**Framework**: {report['framework']}")
    lines.append(f"**Standard**: {report['standard']}")
    lines.append(f"**Date**: {report_date}")
    lines.append("")
    lines.append("## Summary")
    lines.append(
        f"Found {len(active_findings)} scanner-detected issues: "
        f"**{len(auto_issues)} auto-fixable**, "
        f"**{len(input_issues)} need your input**, "
        f"plus a manual checklist below. "
        f"({len(manual_issues)} scanner-flagged items require manual review.)"
    )
    by_scanner = report["summary"].get("by_scanner", {})
    if any(by_scanner.values()):
        scanner_parts = [
            f"{scanner} {count}"
            for scanner, count in by_scanner.items()
            if count
        ]
        lines.append(f"By source: {', '.join(scanner_parts)}.")
    by_confidence = report["summary"].get("by_confidence", {})
    if any(by_confidence.values()):
        confidence_parts = [
            f"{confidence} {count}"
            for confidence, count in by_confidence.items()
            if count
        ]
        lines.append(f"By confidence: {', '.join(confidence_parts)}.")
    status_counts = report["summary"].get("status_counts", {})
    if status_counts.get("waived") or status_counts.get("fixed") or status_counts.get("resolved") or status_counts.get("stale"):
        status_parts = [
            f"{status} {count}"
            for status, count in status_counts.items()
            if status != "open" and count
        ]
        lines.append(f"Tracked statuses: {', '.join(status_parts)}.")
    lines.append("")
    lines.append("---\n")

    lines.append(f"## Group 1: Auto-fixable ({len(auto_issues)} issues)")
    lines.append("")
    if auto_issues:
        lines.append('The agent can apply these fixes without further input. Reply **"go"** to proceed, or list which to skip.\n')
        for index, finding in enumerate(auto_issues, start=1):
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_display_location(finding)}")
            lines.append(f"**Issue**: {_finding_message(finding, message_lookup)}")
            lines.append("**Fix**:")
            lines.append(finding["proposed_fix"]["diff"] or "*(No automatic fix template available)*")
            lines.append("")
    else:
        lines.append("_None._\n")
    lines.append("---\n")

    lines.append(f"## Group 2: Needs your input ({len(input_issues)} issues)")
    lines.append("")
    if input_issues:
        lines.append("These need a decision from you. The agent can draft each fix once you answer.\n")
        for index, finding in enumerate(input_issues, start=1):
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_display_location(finding)}")
            lines.append(f"**Issue**: {_finding_message(finding, message_lookup)}")
            lines.append(f"**Decision needed**: {finding['decision_required']['question']}")
            current_code = finding["evidence"]["snippet"] or finding["evidence"]["dom_snippet"]
            if current_code:
                lines.append("**Current code**:")
                lines.append(f"```\n{current_code}\n```")
            lines.append("")
    else:
        lines.append("_None._\n")
    lines.append("---\n")

    lines.append("## Group 3: Manual checklist")
    lines.append("")
    if manual_issues:
        lines.append("These findings require manual verification before remediation decisions are made.\n")
        for index, finding in enumerate(manual_issues, start=1):
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_display_location(finding)}")
            lines.append(f"**Issue**: {_finding_message(finding, message_lookup)}")
            lines.append("")
    lines.append("These require you to test with actual assistive technology or in the browser. "
                 "Automated tools catch roughly a third of accessibility issues — the rest live here.")
    lines.append("")
    lines.extend(_render_manual_checklist(manual_items, step_failures))
    lines.append("---\n")

    if waived_findings:
        lines.append(f"## Waived findings ({len(waived_findings)})")
        lines.append("")
        for index, finding in enumerate(waived_findings, start=1):
            waiver = finding["waiver"] or {}
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_display_location(finding)}")
            lines.append(f"**Reason**: {waiver.get('reason', '')}")
            lines.append(f"**Approved by**: {waiver.get('approved_by', '')}")
            lines.append(f"**Expires**: {waiver.get('expires_at', '')}")
            lines.append("")
        lines.append("---\n")

    if historical_findings:
        lines.append(f"## Historical statuses ({len(historical_findings)})")
        lines.append("")
        lines.append("These findings were carried from status records and are kept for tracking, not active remediation:")
        lines.append("")
        for index, finding in enumerate(historical_findings, start=1):
            lines.append(f"### {index}. [WCAG {finding['wcag'][0] if finding['wcag'] else 'best-practice'}] — {finding['title']}")
            lines.append(f"**Location**: {_display_location(finding)}")
            lines.append(f"**Status**: {finding['status']}")
            lines.append(f"**Reason**: {finding['group_reason']}")
            lines.append("")
        lines.append("---\n")

    lines.append("## Not checked by this audit")
    lines.append("")
    lines.append("These WCAG criteria are outside what the scanners can evaluate. "
                 "The audit above is incomplete without addressing these separately:")
    lines.extend(_render_not_checked_lines(not_checked_findings))

    return "\n".join(lines)


def _build_message_lookup(issues: List[dict]) -> Dict[str, str]:
    return {
        _fingerprint(issue, _infer_scanner(issue)): issue.get("message", "")
        for issue in issues
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", type=str, help="Path to static scanner JSON")
    parser.add_argument("--runtime", type=str, help="Path to runtime scanner JSON")
    parser.add_argument("--stateful", type=str, help="Path to stateful scanner JSON")
    parser.add_argument("--output", type=str, help="Output markdown path (default: stdout)")
    parser.add_argument("--json-output", type=str, help="Output normalized JSON report")
    parser.add_argument("--status-file", type=str, help="Optional JSON file with status/waiver records")
    parser.add_argument("--detected-at", type=str, help="Override detected_at timestamp (for tests)")
    args = parser.parse_args()

    if not (args.static or args.runtime or args.stateful):
        parser.error("Provide --static, --runtime, --stateful, or any combination.")

    static_data = json.loads(Path(args.static).read_text()) if args.static else None
    runtime_data = json.loads(Path(args.runtime).read_text()) if args.runtime else None
    stateful_data = json.loads(Path(args.stateful).read_text()) if args.stateful else None

    detected_at = args.detected_at or _now_iso()
    output_dir = _output_dir(args.output, args.json_output)
    status_records = load_status_records(args.status_file)
    report = build_report_data(static_data, runtime_data, stateful_data, output_dir, detected_at, status_records)

    raw_issues = []
    if static_data:
        raw_issues.extend(static_data.get("issues", []))
    if runtime_data:
        raw_issues.extend(runtime_data.get("issues", []))
    if stateful_data:
        raw_issues.extend(stateful_data.get("issues", []))
    message_lookup = _build_message_lookup(deduplicate(raw_issues))

    manual_items = generate_manual_review_items(report, stateful_data)
    step_failures = list((stateful_data or {}).get("step_failures", []))
    markdown_report = build_markdown_report(report, message_lookup, manual_items, step_failures)

    if args.output:
        Path(args.output).write_text(markdown_report, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(markdown_report)

    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"JSON report written to {args.json_output}", file=sys.stderr)


if __name__ == "__main__":
    main()
