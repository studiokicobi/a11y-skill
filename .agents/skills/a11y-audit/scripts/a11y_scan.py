#!/usr/bin/env python3
"""
a11y_scan.py — static accessibility scanner for web source files.

Walks a directory, detects framework, runs rule checks against source files,
emits JSON findings for the triage step.

Usage:
    python a11y_scan.py <path> [--output results.json] [--framework auto|react|vue|angular|svelte|html]

No third-party dependencies. Python 3.8+.

Architecture: tag-oriented rules match full-file text with re.DOTALL so they
catch tags that span multiple lines (the common case in React/Vue/Angular
source formatting). Line-oriented rules (CSS color values, outline: none)
still scan line-by-line because they act on declarations, not tags.

The scanner is intentionally conservative — false positives are worse than
false negatives here, because the triage step trusts the output. When a rule
can't decide with high confidence, it emits an issue with triage_hint="input"
so the triage step routes it to Group 2 (needs human input) rather than
Group 1.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional

SUPPORTED_EXTENSIONS = {
    ".html", ".htm",
    ".jsx", ".tsx", ".js", ".ts",
    ".vue",
    ".svelte",
    ".css", ".scss", ".sass", ".less",
}

# Compound suffixes that Path.suffix can't detect (because it only returns the
# final extension). Matched via str.endswith against the filename.
COMPOUND_SUFFIXES = (".component.html",)

SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt",
             "coverage", "__pycache__", ".svelte-kit", "out", ".cache"}


@dataclass
class Issue:
    rule_id: str
    wcag: str
    file: str
    line: int
    col: int
    snippet: str
    message: str
    framework: str
    triage_hint: str  # "auto" | "input" | "manual"
    fix_data: dict = field(default_factory=dict)


def detect_framework(root: Path) -> str:
    # `package.fixture.json` is an alternate manifest name reserved for test
    # fixtures in this repo. Real projects always use `package.json`; fixtures
    # use the alternate so GitHub's dependency graph (Dependabot) does not
    # scan pinned versions and raise CVEs for dependencies that are never
    # installed or executed. Real-world scans still look at `package.json`
    # first, so user behavior is unchanged.
    pkg = root / "package.json"
    if not pkg.exists():
        pkg = root / "package.fixture.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "next" in deps:
                return "nextjs"
            if "react" in deps:
                return "react"
            if "vue" in deps or "nuxt" in deps:
                return "vue"
            if "@angular/core" in deps:
                return "angular"
            if "svelte" in deps or "@sveltejs/kit" in deps:
                return "svelte"
        except (json.JSONDecodeError, OSError):
            pass

    # Fall back to file extensions. Angular's `.component.html` files are a
    # compound suffix that Path.suffix doesn't see, so we track them separately.
    counts = _count_extensions(root)
    if counts.get("component.html", 0) > 0:
        return "angular"
    if counts.get(".tsx", 0) + counts.get(".jsx", 0) > 0:
        return "react"
    if counts.get(".vue", 0) > 0:
        return "vue"
    if counts.get(".svelte", 0) > 0:
        return "svelte"
    return "html"


def _count_extensions(root: Path) -> dict:
    counts = {}
    if root.is_file():
        return counts
    for p in root.rglob("*"):
        if any(skip in p.parts for skip in SKIP_DIRS):
            continue
        if not p.is_file():
            continue
        if p.name.endswith(".component.html"):
            counts["component.html"] = counts.get("component.html", 0) + 1
        counts[p.suffix] = counts.get(p.suffix, 0) + 1
    return counts


def iter_source_files(root: Path):
    if root.is_file():
        yield root
        return
    for p in root.rglob("*"):
        if any(skip in p.parts for skip in SKIP_DIRS):
            continue
        if not p.is_file():
            continue
        if p.suffix in SUPPORTED_EXTENSIONS:
            yield p
        elif any(p.name.endswith(s) for s in COMPOUND_SUFFIXES):
            yield p


def pos_to_line_col(text: str, pos: int) -> tuple:
    """Return (line_number, column), 1-indexed, from a character offset."""
    line = text.count("\n", 0, pos) + 1
    last_nl = text.rfind("\n", 0, pos)
    col = pos - last_nl if last_nl >= 0 else pos + 1
    return line, col


def snippet_around(text: str, start: int, end: int, max_len: int = 200) -> str:
    """Return the matched substring, collapsed to one line for display."""
    raw = text[start:end]
    collapsed = re.sub(r"\s+", " ", raw).strip()
    if len(collapsed) > max_len:
        collapsed = collapsed[:max_len] + "…"
    return collapsed


# -----------------------------------------------------------------------------
# Tag-oriented rules — match the full file text with re.DOTALL so multiline
# tags are handled. [^>]* with DOTALL handles any attribute content that
# doesn't contain a literal > (rare in a11y-relevant attributes).
# -----------------------------------------------------------------------------

IMG_TAG_RE = re.compile(r"<img\b([^>]*?)/?>", re.IGNORECASE | re.DOTALL)
ALT_ATTR_RE = re.compile(r'\balt\s*=\s*("[^"]*"|\'[^\']*\'|\{[^}]*\})',
                         re.IGNORECASE | re.DOTALL)

CLICKABLE_NON_INTERACTIVE_RE = re.compile(
    r"<(div|span|p|h[1-6]|li|td|tr|section|article)\b([^>]*?)>",
    re.IGNORECASE | re.DOTALL,
)
# Click handlers across frameworks:
#   React/Vue:  onClick={...}, onclick="..."
#   Svelte:     on:click={...}
#   Angular:    (click)="..."
# The rule matches any of these in an element's attribute body.
ON_CLICK_RE = re.compile(
    r"(?:\bon[Cc]lick\s*=|\bon:click\s*=|\(click\)\s*=)",
    re.IGNORECASE,
)
# Interactive ARIA roles that make a non-semantic element keyboard-focusable
# when paired with a tabindex. A <div role="button" tabindex="0" onClick>
# behaves like a real button and should not be flagged as a missed handler.
INTERACTIVE_ROLE_RE = re.compile(
    r'\brole\s*=\s*["\']'
    r'(button|link|checkbox|radio|menuitem|menuitemcheckbox|menuitemradio|option|switch|tab)'
    r'["\']',
    re.IGNORECASE,
)
TABINDEX_ATTR_RE = re.compile(r'\btabindex\s*=\s*["\']?(-?\d+)["\']?', re.IGNORECASE)

REDUNDANT_ROLE_TAG_RE = re.compile(
    r"<(nav|main|button|article|section)\b([^>]*?)>",
    re.IGNORECASE | re.DOTALL,
)
ROLE_ATTR_RE = re.compile(r'\brole\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

ANCHOR_TAG_RE = re.compile(r"<a\b([^>]*?)>", re.IGNORECASE | re.DOTALL)
TARGET_BLANK_RE = re.compile(r'\btarget\s*=\s*["\']_blank["\']', re.IGNORECASE)
REL_NOOPENER_RE = re.compile(r'\brel\s*=\s*["\'][^"\']*noopener', re.IGNORECASE)

HTML_TAG_RE = re.compile(r"<html\b([^>]*?)>", re.IGNORECASE | re.DOTALL)
LANG_ATTR_RE = re.compile(r"\blang\s*=", re.IGNORECASE)

INPUT_TAG_RE = re.compile(r"<input\b([^>]*?)/?>", re.IGNORECASE | re.DOTALL)
LABEL_FOR_RE = re.compile(r'<label\b[^>]*?\bfor\s*=\s*["\']([^"\']+)["\']',
                          re.IGNORECASE | re.DOTALL)
LABEL_BLOCK_RE = re.compile(r'<label\b[^>]*?>.*?</label>',
                            re.IGNORECASE | re.DOTALL)
ID_ATTR_RE = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
ARIA_LABEL_RE = re.compile(r'\baria-label(?:ledby)?\s*=', re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r'\bplaceholder\s*=\s*["\']([^"\']+)["\']',
                            re.IGNORECASE)
TYPE_ATTR_RE = re.compile(r'\btype\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
NAME_ATTR_RE = re.compile(r'\bname\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)

MEDIA_AUTOPLAY_RE = re.compile(
    r"<(video|audio)\b([^>]*?)>", re.IGNORECASE | re.DOTALL)
AUTOPLAY_ATTR_RE = re.compile(r'\bautoplay\b', re.IGNORECASE)

TABINDEX_RE = re.compile(
    r'\btab[Ii]ndex\s*=\s*(?:["\'](\d+)["\']|\{(\d+)\})',
    re.IGNORECASE,
)

FOCUSABLE_ARIA_HIDDEN_RE = re.compile(
    r"<(a|button|input|select|textarea)\b([^>]*?)>",
    re.IGNORECASE | re.DOTALL,
)
ARIA_HIDDEN_TRUE_RE = re.compile(r'\baria-hidden\s*=\s*["\']true["\']',
                                 re.IGNORECASE)

# Duplicate id detection uses the existing ID_ATTR_RE to collect every
# id value and its offset within the file.
ID_ATTR_WITH_POS_RE = re.compile(
    r'\bid\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

ICON_CONTROL_RE = re.compile(
    r"<(button|a)\b([^>]*?)>(.*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)
ICON_INDICATOR_RE = re.compile(
    r"<(svg|i|use|path|img)\b",
    re.IGNORECASE,
)
ARIA_LABELLEDBY_RE = re.compile(r'\baria-label(?:ledby)?\s*=\s*["\'][^"\']+["\']',
                                re.IGNORECASE)
TITLE_ATTR_VALUE_RE = re.compile(r'\btitle\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
ALT_ATTR_VALUE_RE = re.compile(r'\balt\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
SR_ONLY_CLASS_RE = re.compile(
    r'\bclass\s*=\s*["\'][^"\']*\b(sr-only|visually-hidden|screen-reader-only|visuallyhidden)\b',
    re.IGNORECASE,
)
HREF_ATTR_RE = re.compile(r'\bhref\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
TAG_STRIP_RE = re.compile(r"<[^>]+>")


def rule_missing_alt(text, path, framework):
    for m in IMG_TAG_RE.finditer(text):
        body = m.group(0)
        if ALT_ATTR_RE.search(body):
            continue
        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="img-missing-alt",
            wcag="1.1.1",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message="<img> missing alt attribute. Screen readers will read the filename or skip it.",
            framework=framework,
            triage_hint="input",
            fix_data={"tag": body[:300], "pattern": "add_alt"},
        )


def rule_clickable_non_interactive(text, path, framework):
    for m in CLICKABLE_NON_INTERACTIVE_RE.finditer(text):
        element = m.group(1).lower()
        attrs = m.group(2)
        if not ON_CLICK_RE.search(attrs):
            continue
        # Skip: element already has an interactive ARIA role + a valid tabindex.
        # That combo (e.g. `<div role="button" tabindex="0" onClick>`) is the
        # documented pattern for custom-built interactive controls and is
        # keyboard-accessible — flagging it would be a false positive.
        if INTERACTIVE_ROLE_RE.search(attrs) and TABINDEX_ATTR_RE.search(attrs):
            continue
        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="clickable-div",
            wcag="2.1.1",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message=(f"<{element}> with onClick is not keyboard-accessible. "
                     f"Use <button type=\"button\"> or <a href> instead."),
            framework=framework,
            triage_hint="auto",
            fix_data={"element": element, "pattern": "div_to_button"},
        )


def rule_redundant_role(text, path, framework):
    implicit = {
        "nav": "navigation",
        "main": "main",
        "button": "button",
        "article": "article",
    }
    for m in REDUNDANT_ROLE_TAG_RE.finditer(text):
        element = m.group(1).lower()
        attrs = m.group(2)
        role_m = ROLE_ATTR_RE.search(attrs)
        if not role_m:
            continue
        role = role_m.group(1).lower()
        if element == "section":
            if role != "region":
                continue
            if not re.search(r'\b(?:aria-label|aria-labelledby)\s*=', attrs, re.IGNORECASE):
                continue
        elif implicit.get(element) != role:
            continue
        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="redundant-role",
            wcag="4.1.2",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message=(f"<{element}> already has implicit role=\"{role}\". "
                     f"Remove the redundant attribute."),
            framework=framework,
            triage_hint="auto",
            fix_data={"element": element, "role": role, "pattern": "remove_role"},
        )


def rule_target_blank(text, path, framework):
    for m in ANCHOR_TAG_RE.finditer(text):
        body = m.group(0)
        if not TARGET_BLANK_RE.search(body):
            continue
        if REL_NOOPENER_RE.search(body):
            continue
        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="target-blank-no-noopener",
            wcag="best-practice",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message="target=\"_blank\" without rel=\"noopener noreferrer\". Security and sometimes accessibility issue.",
            framework=framework,
            triage_hint="auto",
            fix_data={"pattern": "add_rel_noopener"},
        )


def rule_html_lang(text, path, framework):
    for m in HTML_TAG_RE.finditer(text):
        if LANG_ATTR_RE.search(m.group(1)):
            continue
        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="html-missing-lang",
            wcag="3.1.1",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message="<html> element missing lang attribute.",
            framework=framework,
            triage_hint="auto",
            fix_data={"pattern": "add_lang"},
        )


def rule_input_label(text, path, framework):
    label_targets = set(LABEL_FOR_RE.findall(text))
    wrapped_input_spans = []

    for label_m in LABEL_BLOCK_RE.finditer(text):
        label_html = label_m.group(0)
        for input_m in INPUT_TAG_RE.finditer(label_html):
            wrapped_input_spans.append((
                label_m.start() + input_m.start(),
                label_m.start() + input_m.end(),
            ))

    for m in INPUT_TAG_RE.finditer(text):
        if any(start <= m.start() < end for start, end in wrapped_input_spans):
            continue

        attrs = m.group(1)
        type_m = TYPE_ATTR_RE.search(attrs)
        input_type = type_m.group(1).lower() if type_m else "text"
        if input_type in {"hidden", "submit", "button", "reset", "image"}:
            continue
        if ARIA_LABEL_RE.search(attrs):
            continue
        id_m = ID_ATTR_RE.search(attrs)
        if id_m and id_m.group(1) in label_targets:
            continue

        line, col = pos_to_line_col(text, m.start())
        placeholder_m = PLACEHOLDER_RE.search(attrs)
        name_m = NAME_ATTR_RE.search(attrs)
        if placeholder_m:
            yield Issue(
                rule_id="input-placeholder-as-label",
                wcag="1.3.1",
                file=str(path),
                line=line,
                col=col,
                snippet=snippet_around(text, m.start(), m.end()),
                message="<input> uses placeholder as only label. Placeholder disappears on input — add a visible <label>.",
                framework=framework,
                triage_hint="auto",
                fix_data={
                    "placeholder": placeholder_m.group(1),
                    "name": name_m.group(1) if name_m else "",
                    "pattern": "placeholder_to_label",
                },
            )
        else:
            yield Issue(
                rule_id="input-missing-label",
                wcag="1.3.1",
                file=str(path),
                line=line,
                col=col,
                snippet=snippet_around(text, m.start(), m.end()),
                message="<input> has no associated <label> and no aria-label.",
                framework=framework,
                triage_hint="input",
                fix_data={"pattern": "add_label"},
            )


def rule_media_autoplay(text, path, framework):
    for m in MEDIA_AUTOPLAY_RE.finditer(text):
        element = m.group(1).lower()
        attrs = m.group(2)
        if not AUTOPLAY_ATTR_RE.search(attrs):
            continue
        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="media-autoplay",
            wcag="1.4.2",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message=f"<{element}> autoplay. Ensure pause controls and no audio, or remove autoplay.",
            framework=framework,
            triage_hint="input",
            fix_data={"pattern": "autoplay_review"},
        )


def rule_positive_tabindex(text, path, framework):
    for m in TABINDEX_RE.finditer(text):
        value = int(m.group(1) or m.group(2))
        if value <= 0:
            continue
        line, col = pos_to_line_col(text, m.start())
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        yield Issue(
            rule_id="positive-tabindex",
            wcag="2.4.3",
            file=str(path),
            line=line,
            col=col,
            snippet=text[line_start:line_end].strip()[:200],
            message=f"tabindex=\"{value}\" breaks natural tab order. Nearly always should be 0 or removed.",
            framework=framework,
            triage_hint="input",
            fix_data={"value": value, "pattern": "tabindex_review"},
        )


def rule_duplicate_id(text, path, framework):
    """Flag every duplicate `id="..."` occurrence after the first in a file.

    HTML requires document-unique ids. Same-file duplicates are a static signal;
    they're commonly fixable without runtime context, though references to the
    renamed id (htmlFor, aria-labelledby, anchors, selectors) still need review.
    """
    first_seen = {}
    for m in ID_ATTR_WITH_POS_RE.finditer(text):
        id_value = m.group(1)
        if id_value in first_seen:
            line, col = pos_to_line_col(text, m.start())
            yield Issue(
                rule_id="duplicate-id",
                wcag="4.1.1",
                file=str(path),
                line=line,
                col=col,
                snippet=snippet_around(text, m.start(), m.end()),
                message=(
                    f'Duplicate id="{id_value}" (first seen at line '
                    f'{first_seen[id_value]}). HTML requires ids to be unique '
                    "within a document."
                ),
                framework=framework,
                triage_hint="auto",
                fix_data={
                    "id": id_value,
                    "first_line": first_seen[id_value],
                    "pattern": "rename_duplicate_id",
                },
            )
        else:
            first_seen[id_value] = pos_to_line_col(text, m.start())[0]


def _control_has_accessible_name(attrs: str, inner_html: str) -> bool:
    if ARIA_LABELLEDBY_RE.search(attrs):
        return True
    if TITLE_ATTR_VALUE_RE.search(attrs):
        return True

    for img_m in IMG_TAG_RE.finditer(inner_html):
        alt_m = ALT_ATTR_VALUE_RE.search(img_m.group(0))
        if alt_m and alt_m.group(1).strip():
            return True

    # Visually-hidden accessible text wrapper (common pattern).
    if SR_ONLY_CLASS_RE.search(inner_html):
        return True

    stripped = TAG_STRIP_RE.sub("", inner_html)
    # Collapse whitespace and entity artefacts that render as empty.
    stripped = re.sub(r"\s+", " ", stripped).strip()
    stripped = stripped.replace("\u00a0", "").strip()
    return bool(stripped)


def rule_icon_only_control(text, path, framework):
    """Flag <button>/<a> elements that only contain icon markup and no accessible name.

    Conservative: only fires when the control has an icon-like child (svg, i,
    use, path, img) AND no text content, visually-hidden label, aria-label,
    aria-labelledby, or title. `alt=""` on a child img counts as no name.
    """
    for m in ICON_CONTROL_RE.finditer(text):
        element = m.group(1).lower()
        attrs = m.group(2) or ""
        inner = m.group(3) or ""

        # Anchors without href are not focusable and are handled elsewhere; skip.
        if element == "a" and not HREF_ATTR_RE.search(attrs):
            continue
        if not ICON_INDICATOR_RE.search(inner):
            continue
        if _control_has_accessible_name(attrs, inner):
            continue

        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="icon-only-control",
            wcag="4.1.2",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message=(
                f"Icon-only <{element}> has no accessible name. Screen readers "
                "will announce nothing or the raw SVG contents."
            ),
            framework=framework,
            triage_hint="input",
            fix_data={"element": element, "pattern": "add_icon_label"},
        )


def rule_aria_hidden_focusable(text, path, framework):
    for m in FOCUSABLE_ARIA_HIDDEN_RE.finditer(text):
        element = m.group(1).lower()
        attrs = m.group(2)
        if not ARIA_HIDDEN_TRUE_RE.search(attrs):
            continue
        # tabindex="-1" + aria-hidden is a consistent pairing. Only flag when
        # the element is still focusable (no negative tabindex).
        tabindex_m = TABINDEX_RE.search(attrs)
        if tabindex_m:
            value = int(tabindex_m.group(1) or tabindex_m.group(2))
            if value < 0:
                continue
        line, col = pos_to_line_col(text, m.start())
        yield Issue(
            rule_id="aria-hidden-focusable",
            wcag="4.1.2",
            file=str(path),
            line=line,
            col=col,
            snippet=snippet_around(text, m.start(), m.end()),
            message=f"aria-hidden=\"true\" on focusable <{element}>. Remove aria-hidden or add tabindex=\"-1\".",
            framework=framework,
            triage_hint="auto",
            fix_data={"element": element, "pattern": "fix_aria_hidden"},
        )


# -----------------------------------------------------------------------------
# Line-oriented rules
# -----------------------------------------------------------------------------

OUTLINE_NONE_RE = re.compile(
    r"outline(?:-style)?\s*:\s*['\"]?(none|0)['\"]?\s*[;,}!]",
    re.IGNORECASE,
)

TAILWIND_BAD_TEXT_RE = re.compile(
    r'\b(text-(?:gray|slate|zinc|neutral|stone)-(?:300|400)|'
    r'text-(?:red|blue|green|yellow|orange|amber|lime|emerald|teal|cyan|sky|indigo|violet|purple|fuchsia|pink|rose)-(?:300|400))\b',
    re.IGNORECASE,
)

CSS_LOW_CONTRAST_RE = re.compile(
    r'color\s*:\s*(#[aA][aA][aA](?:[aA][aA][aA])?|#[bB][bB][bB](?:[bB][bB][bB])?|#[9][9][9](?:[9][9][9])?|#ccc(?:ccc)?)\b',
    re.IGNORECASE,
)


def line_rule_outline_none(line_no, line, full_text, path, framework):
    for m in OUTLINE_NONE_RE.finditer(line):
        lines = full_text.splitlines()
        window = "\n".join(lines[max(0, line_no - 5):min(len(lines), line_no + 10)])
        if "focus-visible" in window or "box-shadow" in window.lower():
            continue
        yield Issue(
            rule_id="outline-none",
            wcag="2.4.7",
            file=str(path),
            line=line_no,
            col=m.start() + 1,
            snippet=line.strip()[:200],
            message="`outline: none` removes the focus indicator. Provide a :focus-visible replacement.",
            framework=framework,
            triage_hint="auto",
            fix_data={"pattern": "add_focus_visible"},
        )


def line_rule_tailwind_contrast(line_no, line, full_text, path, framework):
    for m in TAILWIND_BAD_TEXT_RE.finditer(line):
        cls = m.group(1)
        yield Issue(
            rule_id="tailwind-low-contrast",
            wcag="1.4.3",
            file=str(path),
            line=line_no,
            col=m.start() + 1,
            snippet=line.strip()[:200],
            message=f"Tailwind class `{cls}` likely fails WCAG AA contrast on light backgrounds.",
            framework=framework,
            triage_hint="auto",
            fix_data={"class": cls, "pattern": "tailwind_swap"},
        )


def line_rule_css_low_contrast(line_no, line, full_text, path, framework):
    for m in CSS_LOW_CONTRAST_RE.finditer(line):
        color = m.group(1)
        yield Issue(
            rule_id="css-low-contrast",
            wcag="1.4.3",
            file=str(path),
            line=line_no,
            col=m.start() + 1,
            snippet=line.strip()[:200],
            message=f"Color {color} likely fails WCAG AA 4.5:1 contrast against white/light backgrounds.",
            framework=framework,
            triage_hint="auto",
            fix_data={"color": color, "pattern": "color_swap"},
        )


TAG_RULES = [
    rule_missing_alt,
    rule_clickable_non_interactive,
    rule_redundant_role,
    rule_target_blank,
    rule_html_lang,
    rule_input_label,
    rule_media_autoplay,
    rule_positive_tabindex,
    rule_aria_hidden_focusable,
    rule_duplicate_id,
    rule_icon_only_control,
]

LINE_RULES = [
    line_rule_outline_none,
    line_rule_tailwind_contrast,
    line_rule_css_low_contrast,
]


def scan_file(path: Path, framework: str) -> List[Issue]:
    issues = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return issues

    for rule in TAG_RULES:
        try:
            issues.extend(rule(text, path, framework))
        except Exception as e:  # noqa: BLE001
            print(f"rule {rule.__name__} failed on {path}: {e}", file=sys.stderr)

    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule in LINE_RULES:
            try:
                issues.extend(rule(line_no, line, text, path, framework))
            except Exception as e:  # noqa: BLE001
                print(f"rule {rule.__name__} failed on {path}:{line_no}: {e}",
                      file=sys.stderr)
    return issues


def main():
    parser = argparse.ArgumentParser(description="Static accessibility scanner.")
    parser.add_argument("path", type=str, help="File or directory to scan")
    parser.add_argument("--output", type=str, default=None,
                        help="Write JSON results to this file")
    parser.add_argument("--framework", type=str, default="auto",
                        choices=["auto", "react", "nextjs", "vue", "angular", "svelte", "html"])
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Path not found: {root}", file=sys.stderr)
        sys.exit(2)

    framework = args.framework
    if framework == "auto":
        framework = detect_framework(root if root.is_dir() else root.parent)

    all_issues = []
    files_scanned = 0
    for fp in iter_source_files(root):
        files_scanned += 1
        all_issues.extend(scan_file(fp, framework))

    result = {
        "target": str(root),
        "framework": framework,
        "files_scanned": files_scanned,
        "issue_count": len(all_issues),
        "issues": [asdict(i) for i in all_issues],
    }

    output_text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        if not args.quiet:
            print(f"Scanned {files_scanned} files, found {len(all_issues)} issues. "
                  f"Results: {args.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
