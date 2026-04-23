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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from baseline import FINGERPRINT_VERSION, build_baseline, compare_findings, load_baseline
from report import build_markdown_report, build_outcome_summary


SCANNER_VERSION = "2.5.0"
STANDARD = "WCAG 2.2 Level AA"
DEFAULT_CONFIDENCE = "medium"
REPORT_GROUPS = ("autofix", "needs_input", "manual_review", "not_checked")
STATUS_VALUES = {"open", "waived", "resolved", "fixed", "stale"}
FIX_SAFETY_VALUES = {"safe", "guarded", "input-required", "manual-only"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
SEVERITY_VALUES = {"minor", "moderate", "serious", "critical", "n/a"}
SCANNER_VALUES = {"static", "runtime", "stateful", "manual-template", "token"}
COVERAGE_PATH = Path(__file__).resolve().parent.parent / "references" / "wcag_coverage.md"
SOURCE_TEXT_CACHE: Dict[str, str] = {}
ID_ATTR_RE = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
DATA_TESTID_ATTR_RE = re.compile(r'\bdata-testid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
NAME_ATTR_RE = re.compile(r'\bname\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
HEADING_TAG_RE = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
SOURCE_LOC_ATTR_RE = re.compile(r'\bdata-source-loc\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
SOURCE_FILE_ATTR_RE = re.compile(r'\bdata-source-file\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
SOURCE_LINE_ATTR_RE = re.compile(r'\bdata-source-line\s*=\s*["\'](\d+)["\']', re.IGNORECASE)
SOURCE_COLUMN_ATTR_RE = re.compile(r'\bdata-source-(?:column|col)\s*=\s*["\'](\d+)["\']', re.IGNORECASE)
COMPONENT_FILE_ATTR_RE = re.compile(r'\bdata-component-file\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
COMPONENT_LINE_ATTR_RE = re.compile(r'\bdata-component-line\s*=\s*["\'](\d+)["\']', re.IGNORECASE)
COMPONENT_STACK_ATTR_RE = re.compile(r'\bdata-component-stack\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
SOURCE_PATH_LINE_RE = re.compile(
    r'([A-Za-z0-9_./\\-]+\.(?:tsx|ts|jsx|js|vue|svelte|html|component\.html)):(\d+)(?::(\d+))?'
)


# Rule → triage group mapping. For anything not in this map, we fall back to
# the issue's triage_hint from the scanner.
RULE_TO_GROUP = {
    # Auto-fixable
    "redundant-role": "auto",
    "target-blank-no-noopener": "auto",
    "input-placeholder-as-label": "auto",
    "tailwind-low-contrast": "auto",
    "css-low-contrast": "auto",
    "outline-none": "auto",
    "aria-hidden-focusable": "auto",

    # Needs input
    "img-missing-alt": "input",
    "input-missing-label": "input",
    "positive-tabindex": "input",
    "media-autoplay": "input",
    "heading-order": "input",
    "icon-only-control": "input",
    "token-low-contrast": "input",
    "token-focus-indicator": "input",
    "token-color-only-semantic": "input",
    # The scanner captures only the opening tag, but swapping a <div> for a
    # <button> (or <a href>) requires rewriting the closing tag too — and the
    # right element depends on whether the control is an action or navigation.
    # Escalate to a decision rather than emit a diff that only rewrites half
    # the element.
    "clickable-div": "input",
    # Renaming an id can break CSS selectors, JS lookups (getElementById,
    # querySelector), ARIA references (aria-labelledby/aria-describedby,
    # for/htmlFor), and anchor hashes — escalate to a decision.
    "duplicate-id": "input",
    # Hard-coding "en" is wrong for any non-English site (and for BCP-47 locales
    # like "en-GB" vs "en-US" that affect screen-reader pronunciation). The
    # agent can't reliably infer the right value, so escalate to a decision.
    "html-missing-lang": "input",
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
    "icon-only-control": "serious",
    "color-contrast": "serious",
    "heading-order": "moderate",
    "token-low-contrast": "serious",
    "token-focus-indicator": "serious",
    "token-color-only-semantic": "moderate",
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
    "icon-only-control": "high",
    "color-contrast": "high",
    "heading-order": "medium",
    "token-low-contrast": "high",
    "token-focus-indicator": "high",
    "token-color-only-semantic": "high",
}


TAILWIND_REPLACEMENTS = {
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


def _tailwind_has_replacement(cls: str) -> bool:
    return cls in TAILWIND_REPLACEMENTS


def _get_tailwind_replacement(cls: str) -> str:
    return TAILWIND_REPLACEMENTS.get(cls, cls)


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


def _read_source_text(path_str: str) -> str:
    if not path_str:
        return ""
    if path_str not in SOURCE_TEXT_CACHE:
        candidate = Path(path_str)
        if not candidate.exists() and not candidate.is_absolute():
            candidate = Path(__file__).resolve().parent.parent / path_str
        try:
            SOURCE_TEXT_CACHE[path_str] = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            SOURCE_TEXT_CACHE[path_str] = ""
    return SOURCE_TEXT_CACHE[path_str]


def _find_repo_root(start: Path) -> Optional[Path]:
    """Walk up from `start` looking for a `.git` marker; return None if absent."""
    try:
        current = start.resolve()
    except (OSError, RuntimeError):
        return None
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _repo_relative_path(value: str) -> str:
    """Normalize a file path for stable, portable fingerprints.

    Absolute paths are rewritten relative to the nearest git repo root so the
    fingerprint is identical regardless of which subdirectory the scanner was
    invoked from. Relative paths are normalized (``.`` / ``..`` segments
    collapsed); a relative path that still escapes its origin with ``..`` is
    resolved against the scanner's cwd so the repo-root rebase can still
    apply. When no repo root can be found we deliberately return the absolute
    path instead of falling back to ``Path.cwd()`` — a cwd-relative fallback
    would make fingerprints depend on which subdirectory the scanner ran
    from, which is exactly what this helper exists to prevent.

    ``file://`` URIs are decoded and normalized like any other local path so
    the fingerprint is stable whether axe-core reports a file as
    ``file:///Users/.../index.html`` or as ``.agents/.../index.html``. Real
    web schemes (``http``/``https``) and opaque non-file URIs pass through
    unchanged.
    """
    if not value:
        return value
    if "://" in value:
        parsed = urlparse(value)
        if parsed.scheme.lower() != "file":
            # Real web URL or other opaque URI — not a local filesystem path.
            return value
        # Decode percent-encoding. We drop the host component entirely: local
        # `file://` URIs typically have an empty host, and a remote host has
        # no meaning for local fingerprints.
        decoded = unquote(parsed.path)
        if not decoded:
            return value
        # Windows-style `file:///C:/foo` decodes to `/C:/foo`; strip the
        # leading slash so the drive letter is preserved correctly.
        if (
            len(decoded) >= 3
            and decoded[0] == "/"
            and decoded[2] == ":"
            and decoded[1].isalpha()
        ):
            decoded = decoded[1:]
        value = decoded
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    try:
        candidate = Path(normalized)
    except (TypeError, ValueError):
        return normalized

    def _posix(path: Path) -> str:
        return str(path).replace("\\", "/")

    if not candidate.is_absolute():
        escapes = normalized.startswith("../") or normalized == ".." or "/../" in normalized
        if not escapes:
            # Plain relative path — collapse redundant segments but keep it
            # relative so fingerprints don't depend on Path.cwd().
            collapsed = os.path.normpath(normalized).replace("\\", "/")
            return collapsed if collapsed != "." else normalized
        # Relative path with `..` segments: resolve against cwd so we can
        # still try to rebase against a repo root. Any failure drops back to
        # a best-effort normpath so fingerprints don't leak cwd by accident.
        try:
            candidate = (Path.cwd() / candidate).resolve()
        except (OSError, RuntimeError):
            return os.path.normpath(normalized).replace("\\", "/")

    repo_root = _find_repo_root(candidate)
    if repo_root:
        try:
            return _posix(candidate.resolve().relative_to(repo_root))
        except (ValueError, OSError):
            pass
    # No repo marker → keep the absolute path. Re-running from a different
    # subdirectory must not silently change the fingerprint.
    try:
        return _posix(candidate.resolve())
    except (OSError, RuntimeError):
        return _posix(candidate)


def _find_attr(snippet: str, pattern: re.Pattern) -> str:
    if not snippet:
        return ""
    match = pattern.search(snippet)
    return match.group(1).strip() if match else ""


def _strip_html(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _associated_label_text(text: str, snippet: str) -> str:
    element_id = _find_attr(snippet, ID_ATTR_RE)
    if not element_id or not text:
        return ""
    pattern = re.compile(
        rf'<label\b[^>]*\bfor\s*=\s*["\']{re.escape(element_id)}["\'][^>]*>(.*?)</label>',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    return _strip_html(match.group(1)) if match else ""


def _nearest_heading_text(text: str, line_number: int) -> str:
    if not text or line_number <= 0:
        return ""
    last_heading = ""
    for match in HEADING_TAG_RE.finditer(text):
        heading_line = text.count("\n", 0, match.start()) + 1
        if heading_line > line_number:
            break
        candidate = _strip_html(match.group(2))
        if candidate:
            last_heading = candidate
    return last_heading


def _normalize_selector_value(selector: str) -> str:
    normalized = re.sub(r"\s+", " ", (selector or "").strip())
    normalized = re.sub(r":nth-child\(\d+\)", ":nth-child(*)", normalized)
    return normalized


def _static_fingerprint_data(issue: dict) -> dict:
    snippet = issue.get("snippet", "")
    source_file = str(issue.get("file", ""))
    source_text = _read_source_text(source_file)

    anchor_value = _find_attr(snippet, ID_ATTR_RE)
    anchor_source = "id" if anchor_value else ""

    if not anchor_value:
        anchor_value = _find_attr(snippet, DATA_TESTID_ATTR_RE)
        anchor_source = "data-testid" if anchor_value else ""

    if not anchor_value:
        anchor_value = _associated_label_text(source_text, snippet)
        anchor_source = "label" if anchor_value else ""

    if not anchor_value:
        anchor_value = _find_attr(snippet, NAME_ATTR_RE)
        anchor_source = "name" if anchor_value else ""

    if not anchor_value:
        anchor_value = _nearest_heading_text(source_text, int(issue.get("line", 0) or 0))
        anchor_source = "heading" if anchor_value else ""

    unstable = False
    if not anchor_value:
        anchor_value = f"line-{issue.get('line', 0)}"
        anchor_source = "line"
        unstable = True

    return {
        "fingerprint_version": FINGERPRINT_VERSION,
        "anchor_source": anchor_source,
        "anchor_value": anchor_value,
        "unstable": unstable,
    }


def _runtime_fingerprint_data(issue: dict, scanner: str) -> dict:
    selector = _normalize_selector_value(issue.get("fix_data", {}).get("target", "") or _signature(issue.get("snippet", "")))
    page_context = _repo_relative_path(str(issue.get("file", "")))
    step_id = issue.get("journey_step_id", "") or issue.get("fix_data", {}).get("journey_step_id", "")
    page_or_step_context = page_context if scanner == "runtime" else f"{page_context}|{step_id}"
    unstable = not bool(selector)
    return {
        "fingerprint_version": FINGERPRINT_VERSION,
        "normalized_selector": selector or "unknown",
        "page_context": page_context,
        "page_or_step_context": page_or_step_context,
        "unstable": unstable,
    }


def _token_fingerprint_data(issue: dict) -> dict:
    token_name = (
        issue.get("fix_data", {}).get("token_name")
        or issue.get("fix_data", {}).get("pair_id")
        or issue.get("fix_data", {}).get("semantic_token")
        or issue.get("fix_data", {}).get("focus_token")
        or f"line-{issue.get('line', 0)}"
    )
    unstable = token_name.startswith("line-")
    return {
        "fingerprint_version": FINGERPRINT_VERSION,
        "anchor_source": "token",
        "anchor_value": str(token_name),
        "unstable": unstable,
    }


def _fingerprint_data(issue: dict, scanner: str) -> dict:
    if scanner == "static":
        return _static_fingerprint_data(issue)
    if scanner == "token":
        return _token_fingerprint_data(issue)
    return _runtime_fingerprint_data(issue, scanner)


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

    if rule_id == "redundant-role":
        role = fix_data.get("role", "")
        before = snippet
        after = snippet
        for pattern in (f' role="{role}"', f" role='{role}'"):
            after = after.replace(pattern, "")
        return diff(before, after)

    if rule_id == "target-blank-no-noopener":
        before = snippet
        rel_match = re.search(
            r"\brel\s*=\s*([\"'])([^\"']*)\1",
            snippet,
            re.IGNORECASE,
        )
        if rel_match:
            quote = rel_match.group(1)
            tokens = rel_match.group(2).split()
            for token in ("noopener", "noreferrer"):
                if token not in tokens:
                    tokens.append(token)
            merged = " ".join(tokens)
            after = (
                snippet[: rel_match.start()]
                + f"rel={quote}{merged}{quote}"
                + snippet[rel_match.end():]
            )
            return diff(before, after)
        # No existing rel= — inject one immediately after target="_blank",
        # tolerating whitespace around `=` and either quote style.
        target_match = re.search(
            r"\btarget\s*=\s*([\"'])\s*_blank\s*\1",
            snippet,
            re.IGNORECASE,
        )
        if not target_match:
            return None
        quote = target_match.group(1)
        insert_at = target_match.end()
        after = (
            snippet[:insert_at]
            + f" rel={quote}noopener noreferrer{quote}"
            + snippet[insert_at:]
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
        before = snippet
        # Accept either quote style (and a bare unquoted value) on both the
        # placeholder attribute and any existing id, so the fix is not a
        # no-op when the source file uses single quotes.
        placeholder_re = re.compile(
            r"placeholder\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>\"']+))",
            re.IGNORECASE,
        )
        id_re = re.compile(
            r"\bid\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>\"']+))",
            re.IGNORECASE,
        )
        tag_re = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)")

        placeholder_match = placeholder_re.search(snippet)
        tag_match = tag_re.match(snippet)
        if not placeholder_match or not tag_match:
            return None

        placeholder_text = (
            placeholder_match.group(1)
            or placeholder_match.group(2)
            or placeholder_match.group(3)
            or fix_data.get("placeholder", "")
        )

        id_match = id_re.search(snippet)
        if id_match:
            input_id = id_match.group(1) or id_match.group(2) or id_match.group(3)
            after_input = snippet
        else:
            input_id = _suggest_input_id(issue, fix_data)
            insert_at = tag_match.end()
            after_input = snippet[:insert_at] + f' id="{input_id}"' + snippet[insert_at:]

        attr_name = "for" if framework in {"vue", "angular", "html", "svelte"} else "htmlFor"
        after = (
            f'<label {attr_name}="{input_id}">{placeholder_text}</label>\n'
            + after_input
        )
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
        # Container case routes to needs_input via classify(), so render_fix
        # should never run for it; belt-and-braces guard in case a caller
        # bypasses classify.
        if fix_data.get("pattern") == "aria_hidden_container":
            return None
        before = snippet
        # Match any quote style or unquoted value, tolerate whitespace
        # around `=`, and greedily capture whitespace on BOTH sides of the
        # attribute. The replacement callback collapses the edit site
        # locally — never touching other whitespace in the snippet — so
        # repeated spaces inside `aria-label="Save   now"` or body text
        # survive the fix unchanged. (Codex round-2 #3.)
        pattern = re.compile(
            r"(\s*)\baria-hidden\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>\"']+)(\s*)",
            flags=re.IGNORECASE,
        )

        def _collapse_edit_site(match: re.Match) -> str:
            leading, trailing = match.group(1), match.group(2)
            # Whitespace on both sides → keep one space so neighboring
            # attributes don't fuse. Whitespace on only one side → drop
            # it; we're adjacent to a tag boundary or another attribute.
            return " " if (leading and trailing) else ""

        after, replaced = pattern.subn(_collapse_edit_site, snippet, count=1)
        if not replaced:
            return None
        return diff(before, after)

    if rule_id == "duplicate-id":
        id_value = fix_data.get("id", "")
        first_line = fix_data.get("first_line", 0)
        if not id_value:
            return None
        renamed = f"{id_value}-2"
        before = snippet
        after = snippet.replace(f'id="{id_value}"', f'id="{renamed}"', 1)
        if after == before:
            after = snippet.replace(f"id='{id_value}'", f"id='{renamed}'", 1)
        suffix = (
            f"\n<!-- note: first occurrence is at line {first_line}. "
            f"Before renaming, search the codebase for `{id_value}` references "
            "(htmlFor, aria-labelledby, anchor #hashes, document.getElementById, "
            "CSS selectors) and update them or rename the other occurrence instead. -->"
        )
        return diff(before, after) + suffix

    if rule_id == "icon-only-control":
        element = fix_data.get("element", "button")
        before = snippet
        insertion = ' aria-label="TODO: describe the action"'
        after = re.sub(
            rf"<{re.escape(element)}\b",
            f"<{element}{insertion}",
            snippet,
            count=1,
            flags=re.IGNORECASE,
        )
        return (
            diff(before, after)
            + "\n<!-- note: replace the TODO with a short verb phrase matching what activating this control does "
            "(e.g. \"Close dialog\", \"Search\", \"Next slide\"). -->"
        )

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
        "icon-only-control": "Icon-only control missing accessible name",
        "color-contrast": "Color contrast failure (runtime)",
        "heading-order": "Heading order skip",
        "token-low-contrast": "Token contrast pair fails WCAG",
        "token-focus-indicator": "Focus indicator token is missing or too weak",
        "token-color-only-semantic": "Semantic token relies on color alone",
    }
    return titles.get(rule_id, rule_id.replace("-", " ").capitalize())


def decision_prompt(issue: dict) -> str:
    rule_id = issue["rule_id"]
    if rule_id == "clickable-div":
        fix_data = issue.get("fix_data", {})
        if fix_data.get("has_interactive_role_and_tabindex"):
            return (
                "role + tabindex does not guarantee keyboard activation. Verify "
                "that an Enter/Space keyboard handler exists, or replace with "
                "a native element."
            )
        return (
            "Is this an action (replace with `<button type=\"button\">`) or "
            "navigation (replace with `<a href=\"…\">`)? The closing tag also "
            "needs to change — the scanner only captured the opening tag."
        )
    if rule_id == "aria-hidden-focusable":
        fix_data = issue.get("fix_data", {})
        if fix_data.get("pattern") == "aria_hidden_container":
            return (
                "A container with aria-hidden=\"true\" has a focusable descendant, "
                "so keyboard users can land on something screen readers ignore. "
                "Pick one: remove aria-hidden from the container, add "
                "tabindex=\"-1\" to the descendant, or move the descendant out "
                "of the hidden subtree."
            )
    prompts = {
        "img-missing-alt": 'What does this image convey? (For decorative images, we\'ll use alt="".)',
        "input-missing-label": "What should this input be labeled?",
        "positive-tabindex": "Is this tab order deliberate? If not, we'll remove the positive tabindex.",
        "media-autoplay": "Keep autoplay with pause controls, or remove autoplay entirely?",
        "icon-only-control": 'What does this control do? We\'ll add an `aria-label` so screen readers announce its purpose.',
        "color-contrast": "Pick an accessible color that aligns with your brand — we'll suggest 2–3 options if you want.",
        "heading-order": "Should the out-of-order heading be downgraded/upgraded to match the sequence, or should we restructure the page hierarchy?",
        "token-low-contrast": "Which nearby compliant token value should replace this failing pair?",
        "token-focus-indicator": "Should we strengthen the focus ring color, width, or both for this token set?",
        "token-color-only-semantic": "What non-color cue should accompany this semantic token across the design system?",
        "tailwind-low-contrast": (
            "This Tailwind color class likely fails WCAG AA 4.5:1 and has no safe "
            "mapping to a compliant shade. Pick a darker shade in the same family "
            "or a different accessible color class."
        ),
        "duplicate-id": (
            "Which element keeps the id, and what should the other one be renamed to? "
            "(Search the codebase first — CSS selectors, JS lookups, "
            "aria-labelledby/aria-describedby, label[for], and anchor #hashes may depend on it.)"
        ),
        "html-missing-lang": (
            "What BCP-47 language tag should go on `<html lang>`? "
            "(e.g. `en`, `en-GB`, `sv`, `fr-CA`. Screen readers use this to pick pronunciation, "
            "so it must match the document's primary language — don't just default to `en`.)"
        ),
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
    rule_id = issue["rule_id"]
    if rule_id == "tailwind-low-contrast":
        cls = issue.get("fix_data", {}).get("class", "")
        if not _tailwind_has_replacement(cls):
            return "input"
    if rule_id == "aria-hidden-focusable":
        # Container case has no single correct autofix — the author must pick
        # between removing aria-hidden, adding tabindex="-1" to the descendant,
        # or restructuring the subtree. Element-self case stays auto.
        if issue.get("fix_data", {}).get("pattern") == "aria_hidden_container":
            return "input"
    if rule_id in RULE_TO_GROUP:
        return RULE_TO_GROUP[rule_id]
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


_REQUIRED_ISSUE_FIELDS = ("rule_id", "file")
_SCANNER_INPUT_HELP = {
    "static": "Expected the output of scripts/a11y_scan.py (a JSON object with an `issues` array).",
    "runtime": "Expected the output of scripts/a11y_runtime.js (a JSON object with an `issues` array).",
    "stateful": "Expected the output of scripts/a11y_stateful.js (a JSON object with an `issues` array).",
    "token": "Expected the output of scripts/tokens.py (a JSON object with an `issues` array).",
}
# For each non-static scanner, at least one of these per-issue signals must be
# present so we can tell this issue actually came from that scanner. Static is
# the only shape with no distinguishing signal, so it's excluded — an issue
# that matches none of these patterns is treated as static.
_REQUIRED_ISSUE_SIGNALS = {
    "runtime": "explicit `scanner: \"runtime\"`, `framework: \"runtime\"`, `origin_rule_id`, or `fix_data.axe_rule`",
    "stateful": "explicit `scanner: \"stateful\"`, `framework: \"stateful\"`, or `journey_step_id` (top-level or in `fix_data`)",
    "token": "explicit `scanner: \"token\"` or `framework: \"token\"`",
}


def _exit_config_error(message: str) -> None:
    """Exit with code 2 (configuration/runtime error) and a clean message."""
    print(f"Configuration error: {message}", file=sys.stderr)
    sys.exit(2)


# Top-level `scanner` labels emitted by each scanner's output. Static
# omits the top-level field entirely (legacy behaviour), but when present
# it must match the declared scanner — otherwise we're almost certainly
# reading the wrong file.
_SCANNER_TOPLEVEL_LABELS = {
    "static": {None, "static"},
    "runtime": {"runtime"},
    "stateful": {"stateful"},
    "token": {"token"},
}


def _issue_signals_scanner(issue: dict) -> Optional[str]:
    """Return the scanner this issue clearly belongs to, if signals are present.

    Returns None when the issue is ambiguous (e.g. a static-shaped issue that
    could come from any source). Used to catch mislabeled payloads — if an
    issue obviously belongs to scanner Y but the caller declared X, we
    reject instead of letting `_infer_scanner` silently reclassify it.
    """
    explicit = issue.get("scanner")
    if explicit in SCANNER_VALUES:
        return explicit
    if issue.get("journey_step_id") or issue.get("fix_data", {}).get("journey_step_id"):
        return "stateful"
    framework = issue.get("framework")
    if framework in {"stateful", "runtime", "token"}:
        return framework
    if issue.get("origin_rule_id") or issue.get("fix_data", {}).get("axe_rule"):
        return "runtime"
    return None


def _validate_scanner_payload(path_str: Optional[str], scanner: str) -> Optional[dict]:
    """Load and shape-validate a scanner JSON payload.

    Raises ValueError with a human-readable message on: missing file,
    invalid JSON, wrong top-level shape, `issues` not a list, any issue
    missing required fields, or mislabeled payload (top-level `scanner`
    or a per-issue signal that disagrees with the declared scanner).

    Callers that want process-exit semantics should use
    `_load_scanner_payload`, which wraps this with `_exit_config_error`.
    """
    if not path_str:
        return None
    path = Path(path_str)
    help_text = _SCANNER_INPUT_HELP.get(scanner, "")
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(f"--{scanner} file not found: {path}")
    except OSError as exc:
        raise ValueError(f"--{scanner} file unreadable: {path} ({exc})")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"--{scanner} file is not valid JSON: {path} (line {exc.lineno}, column {exc.colno}: {exc.msg}). {help_text}"
        )
    if not isinstance(data, dict):
        raise ValueError(
            f"--{scanner} file must be a JSON object, got {type(data).__name__}: {path}. {help_text}"
        )
    top_level_scanner = data.get("scanner")
    allowed_top_level = _SCANNER_TOPLEVEL_LABELS.get(scanner, {None, scanner})
    if top_level_scanner not in allowed_top_level:
        raise ValueError(
            f"--{scanner} file declares top-level `scanner` of {top_level_scanner!r}, "
            f"expected {sorted(str(v) for v in allowed_top_level)}: {path}. {help_text}"
        )
    issues = data.get("issues")
    if issues is None:
        # Empty payloads (no issues field) are treated as zero issues rather
        # than an error — some scanners omit the key when they found nothing.
        data["issues"] = []
        return data
    if not isinstance(issues, list):
        raise ValueError(
            f"--{scanner} file has `issues` of type {type(issues).__name__}, expected list: {path}. {help_text}"
        )
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise ValueError(
                f"--{scanner} issue #{index} is {type(issue).__name__}, expected object: {path}."
            )
        missing = [field for field in _REQUIRED_ISSUE_FIELDS if field not in issue]
        if missing:
            raise ValueError(
                f"--{scanner} issue #{index} missing required field(s) {missing}: {path}."
            )
        signalled = _issue_signals_scanner(issue)
        if signalled is not None and signalled != scanner:
            raise ValueError(
                f"--{scanner} issue #{index} looks like {signalled!r} output "
                f"(scanner/framework/journey_step_id signals): {path}. {help_text}"
            )
        # Non-static scanners must positively signal themselves on every
        # issue. Without this the normalizer routes ambiguous rows through
        # `_infer_scanner`, where they fall through to "static" — so a
        # malformed runtime.json would triage as static-shaped findings
        # while the report still claims runtime coverage (the regression
        # Codex round-2 #1 found).
        if scanner != "static" and signalled is None:
            expected = _REQUIRED_ISSUE_SIGNALS.get(scanner, "")
            raise ValueError(
                f"--{scanner} issue #{index} has no {scanner}-specific signals; "
                f"expected {expected}: {path}. {help_text}"
            )
    return data


def _load_scanner_payload(path_str: Optional[str], scanner: str) -> Optional[dict]:
    """CLI-entry wrapper: validate, or exit with code 2 on any failure."""
    try:
        return _validate_scanner_payload(path_str, scanner)
    except ValueError as exc:
        _exit_config_error(str(exc))
        return None  # unreachable: sys.exit above


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


def _fingerprint(issue: dict, scanner: str) -> Tuple[str, dict]:
    data = _fingerprint_data(issue, scanner)
    if scanner in {"static", "token"}:
        fingerprint = "|".join([
            issue["rule_id"],
            _repo_relative_path(str(issue.get("file", ""))),
            data["anchor_source"],
            data["anchor_value"],
        ])
        return fingerprint, data

    fingerprint = "|".join([
        issue["rule_id"],
        data["normalized_selector"],
        data["page_or_step_context"],
    ])
    return fingerprint, data


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


def _blast_radius(issue: dict) -> Optional[dict]:
    value = issue.get("fix_data", {}).get("blast_radius")
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return None


def _mapping_from_source_loc(snippet: str) -> Optional[dict]:
    match = SOURCE_LOC_ATTR_RE.search(snippet or "")
    if not match:
        return None
    loc_match = SOURCE_PATH_LINE_RE.search(match.group(1))
    if not loc_match:
        return None
    source_file = loc_match.group(1).replace("\\", "/")
    source_line = int(loc_match.group(2))
    explanation = "Mapped from debug DOM attribute data-source-loc."
    return {
        "source_file": source_file,
        "source_line": source_line,
        "confidence": "high",
        "explanation": explanation,
    }


def _mapping_from_source_attrs(snippet: str) -> Optional[dict]:
    source_file = _find_attr(snippet, SOURCE_FILE_ATTR_RE)
    if not source_file:
        return None
    line_match = SOURCE_LINE_ATTR_RE.search(snippet or "")
    source_line = int(line_match.group(1)) if line_match else 0
    confidence = "high" if source_line else "medium"
    explanation = "Mapped from debug DOM attributes data-source-file/data-source-line."
    if not source_line:
        explanation = "Mapped from debug DOM attribute data-source-file without a precise source line."
    return {
        "source_file": source_file.replace("\\", "/"),
        "source_line": source_line,
        "confidence": confidence,
        "explanation": explanation,
    }


def _mapping_from_component_attrs(snippet: str) -> Optional[dict]:
    source_file = _find_attr(snippet, COMPONENT_FILE_ATTR_RE)
    if source_file:
        line_match = COMPONENT_LINE_ATTR_RE.search(snippet or "")
        source_line = int(line_match.group(1)) if line_match else 0
        return {
            "source_file": source_file.replace("\\", "/"),
            "source_line": source_line,
            "confidence": "medium",
            "explanation": "Mapped from debug component-file attributes exposed in the rendered DOM.",
        }

    stack_match = COMPONENT_STACK_ATTR_RE.search(snippet or "")
    if not stack_match:
        return None
    loc_match = SOURCE_PATH_LINE_RE.search(stack_match.group(1))
    if not loc_match:
        return None
    return {
        "source_file": loc_match.group(1).replace("\\", "/"),
        "source_line": int(loc_match.group(2)),
        "confidence": "medium",
        "explanation": "Mapped from a debug component stack attribute exposed in the rendered DOM.",
    }


def _normalize_mapping(issue: dict, scanner: str) -> dict:
    if scanner in {"static", "token"}:
        location = _normalize_location(issue)
        explanation = "Mapped directly from the source scanner location."
        if scanner == "token":
            explanation = "Mapped directly from the token source file."
        return {
            "source_file": location["file"],
            "source_line": location["line"],
            "confidence": "high",
            "explanation": explanation,
        }

    snippet = issue.get("snippet", "")
    for builder in (_mapping_from_source_loc, _mapping_from_source_attrs, _mapping_from_component_attrs):
        mapping = builder(snippet)
        if mapping:
            return mapping

    return {
        "source_file": "",
        "source_line": 0,
        "confidence": "low",
        "explanation": "No source mapping hints were available in the runtime DOM evidence.",
    }


def normalize_finding(issue: dict, detected_at: str, output_dir: Path) -> dict:
    scanner = _infer_scanner(issue)
    triage_group = {
        "auto": "autofix",
        "input": "needs_input",
        "manual": "manual_review",
    }.get(classify(issue), "needs_input")
    fingerprint, fingerprint_data = _fingerprint(issue, scanner)
    mapping = _normalize_mapping(issue, scanner)
    if scanner in {"runtime", "stateful"} and triage_group == "autofix" and mapping["confidence"] == "low":
        triage_group = "needs_input"
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
        "mapping": mapping,
        "evidence": _normalize_evidence(issue, output_dir),
        "decision_required": _decision_required(issue, triage_group),
        "proposed_fix": _proposed_fix(issue, triage_group),
        "fingerprint": fingerprint,
        "fingerprint_data": fingerprint_data,
        "confirmed_by": _confirmed_by(issue, scanner),
    }
    origin_rule_id = _origin_rule_id(issue)
    if origin_rule_id:
        normalized["origin_rule_id"] = origin_rule_id
    blast_radius = _blast_radius(issue)
    if blast_radius:
        normalized["blast_radius"] = blast_radius
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


def apply_status_overrides(findings: List[dict], records: List[dict], detected_at: str) -> None:
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


def historical_findings_from_records(findings: List[dict], records: List[dict], detected_at: str) -> List[dict]:
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
    return historical


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
    if "baseline_comparison" in report and not isinstance(report["baseline_comparison"], dict):
        raise ValueError("baseline_comparison must be an object when present")
    if not isinstance(report["findings"], list):
        raise ValueError("Report findings must be an array")
    for finding in report["findings"]:
        validate_finding_schema(finding)


def build_report_data(
    static_data: Optional[dict],
    runtime_data: Optional[dict],
    stateful_data: Optional[dict],
    token_data: Optional[dict],
    baseline_data: Optional[dict],
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
    if token_data:
        issues.extend(token_data.get("issues", []))

    current_findings = [
        normalize_finding(issue, detected_at, output_dir)
        for issue in deduplicate(issues)
    ]
    apply_status_overrides(current_findings, status_records, detected_at)
    compared_findings, baseline_summary = compare_findings(current_findings, baseline_data)
    historical_findings = historical_findings_from_records(compared_findings, status_records, detected_at)
    normalized_findings = compared_findings + historical_findings
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
        (static_data or runtime_data or token_data or {}).get("target")
        or ", ".join((runtime_data or {}).get("urls", []))
        or ", ".join(journey.get("start_url", "") for journey in (stateful_data or {}).get("journeys", []))
    )
    framework = (
        (static_data or {}).get("framework")
        or (token_data or {}).get("scanner")
        or ("stateful" if stateful_data else "unknown")
    )

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
        "baseline_comparison": baseline_summary,
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


def _token_only_manual_items() -> List[dict]:
    """Checklist for token-only audits (no page-flow checks).

    Returned when the user scanned only design tokens — there is no rendered
    page to tab through, so page-flow checks like keyboard tab order, focus
    return, heading outline, and zoom/reflow don't apply. What still applies:
    design-system-level checks the token scan can't catch on its own.
    """
    return [
        {
            "title": "Use-of-color-only communication across semantic tokens",
            "capability": "visual",
            "wcag": ["1.4.1"],
            "context": "Inspect tokens that convey meaning (success, error, warning, info, selected, disabled).",
            "steps": [
                "Preview each semantic token pair in a color-blindness simulator or grayscale.",
                "Check that the paired icon, label, or shape token is mandatory (not optional) in the component spec.",
            ],
            "expected": [
                "Meaning survives without hue perception.",
                "The design system documents the non-color companion cue for every semantic state.",
            ],
        },
        {
            "title": "Theme coverage for every semantic token",
            "capability": "design system",
            "wcag": ["1.4.3", "1.4.11"],
            "context": "If the product supports multiple themes (light/dark, high-contrast, branded), each semantic token needs a value in every theme.",
            "steps": [
                "Open the token source and confirm each semantic token has a value in every supported theme.",
                "Spot-check contrast pairs in each theme with the contrast checker.",
            ],
            "expected": [
                "No token resolves to `undefined` or inherits an inappropriate parent value in any theme.",
                "Each theme passes the contrast rules the default theme passes.",
            ],
        },
        {
            "title": "Rendered composition at component boundaries",
            "capability": "visual",
            "wcag": ["1.4.3", "1.4.11"],
            "context": "The token scan checks declared token pairs. It cannot see how components compose them (e.g., disabled text on a disabled background, tooltip on a translucent overlay).",
            "steps": [
                "List the component states that combine multiple tokens (disabled, hover, focus, selected, overlay).",
                "Render each combination and measure the effective contrast against the background it actually lands on.",
            ],
            "expected": [
                "Every rendered combination meets the relevant contrast ratio.",
                "Tokens that only pass in isolation are flagged in the design system as 'do not combine with X'.",
            ],
        },
    ]


def generate_manual_review_items(
    report: dict,
    stateful_data: Optional[dict],
    scanners_ran: Optional[List[str]] = None,
) -> List[dict]:
    # Token-only runs have no rendered page to exercise — swap in a
    # design-system-scoped checklist instead of asking users to tab through
    # a page that doesn't exist in this audit.
    if scanners_ran and set(scanners_ran) == {"token"}:
        return _token_only_manual_items()
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
            "wcag": ["1.4.4", "1.4.10", "1.4.12"],
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
            "wcag": ["2.3.3"],
            "context": "Repeat the audited journey with reduced motion enabled if the UI animates. (2.3.1 Three-flashes is not covered here — it needs a visual frame-rate pass.)",
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
            "title": "Dragging gestures have a non-drag alternative",
            "capability": "pointer",
            "wcag": ["2.5.7"],
            "context": "Inspect any control that relies on a click-hold-drag gesture (reorder handles, sliders, sortable lists, draggable cards, pan/zoom surfaces).",
            "steps": [
                "Identify every drag-based interaction in the audited page or flow.",
                "Verify each one has a single-pointer alternative (keyboard arrow keys, up/down buttons, context menu, typed input) unless the dragging is essential.",
            ],
            "expected": [
                "No feature requires dragging to complete unless dragging is essential to the task.",
                "Single-pointer alternatives are discoverable, labeled, and reachable by keyboard.",
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




def _build_message_lookup(issues: List[dict]) -> Dict[str, str]:
    return {
        _fingerprint(issue, _infer_scanner(issue))[0]: issue.get("message", "")
        for issue in issues
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", type=str, help="Path to static scanner JSON")
    parser.add_argument("--runtime", type=str, help="Path to runtime scanner JSON")
    parser.add_argument("--stateful", type=str, help="Path to stateful scanner JSON")
    parser.add_argument("--tokens", type=str, help="Path to token scanner JSON")
    parser.add_argument("--baseline-file", type=str, help="Optional baseline JSON to compare against")
    parser.add_argument("--write-baseline", type=str, help="Optional path to write a fresh baseline JSON")
    parser.add_argument("--output", type=str, help="Output markdown path (default: stdout)")
    parser.add_argument("--json-output", type=str, help="Output normalized JSON report")
    parser.add_argument("--status-file", type=str, help="Optional JSON file with status/waiver records")
    parser.add_argument("--detected-at", type=str, help="Override detected_at timestamp (for tests)")
    args = parser.parse_args()

    if not (args.static or args.runtime or args.stateful or args.tokens):
        parser.error("Provide --static, --runtime, --stateful, --tokens, or any combination.")

    static_data = _load_scanner_payload(args.static, "static")
    runtime_data = _load_scanner_payload(args.runtime, "runtime")
    stateful_data = _load_scanner_payload(args.stateful, "stateful")
    token_data = _load_scanner_payload(args.tokens, "token")
    try:
        baseline_data = load_baseline(args.baseline_file)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Baseline error: {exc}", file=sys.stderr)
        sys.exit(3)

    detected_at = args.detected_at or _now_iso()
    output_dir = _output_dir(args.output, args.json_output)
    status_records = load_status_records(args.status_file)
    report = build_report_data(static_data, runtime_data, stateful_data, token_data, baseline_data, output_dir, detected_at, status_records)

    raw_issues = []
    if static_data:
        raw_issues.extend(static_data.get("issues", []))
    if runtime_data:
        raw_issues.extend(runtime_data.get("issues", []))
    if stateful_data:
        raw_issues.extend(stateful_data.get("issues", []))
    if token_data:
        raw_issues.extend(token_data.get("issues", []))
    message_lookup = _build_message_lookup(deduplicate(raw_issues))

    scanners_ran_for_checklist = [
        scanner
        for scanner, payload in (
            ("static", static_data),
            ("runtime", runtime_data),
            ("stateful", stateful_data),
            ("token", token_data),
        )
        if payload
    ]
    manual_items = generate_manual_review_items(
        report, stateful_data, scanners_ran=scanners_ran_for_checklist
    )
    step_failures = list((stateful_data or {}).get("step_failures", []))
    artifact_paths = []
    if args.json_output:
        artifact_paths.append(Path(args.json_output).name)
    markdown_report = build_markdown_report(
        report,
        message_lookup,
        manual_items,
        step_failures,
        render_context={
            "mode": "triage",
            "artifact_paths": artifact_paths,
            "scanners_ran": [
                scanner
                for scanner, payload in (
                    ("static", static_data),
                    ("runtime", runtime_data),
                    ("stateful", stateful_data),
                    ("token", token_data),
                )
                if payload
            ],
        },
    )

    if args.output:
        Path(args.output).write_text(markdown_report, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(markdown_report)

    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"JSON report written to {args.json_output}", file=sys.stderr)

    if args.write_baseline:
        baseline_output = build_baseline(report)
        Path(args.write_baseline).write_text(json.dumps(baseline_output, indent=2), encoding="utf-8")
        print(f"Baseline written to {args.write_baseline}", file=sys.stderr)


if __name__ == "__main__":
    main()
