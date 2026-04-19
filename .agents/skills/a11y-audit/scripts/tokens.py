#!/usr/bin/env python3
"""
tokens.py — narrow design-token accessibility analysis.

Supports one explicit JSON token schema for Phase 3:
- color contrast pairs
- focus indicator tokens
- color-only semantic tokens

Usage:
    python3 tokens.py path/to/tokens.json --output /tmp/tokens.json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from contrast_checker import contrast_ratio, suggest_alternative


HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_tokens(node: object, prefix: str = "") -> Dict[str, str]:
    values: Dict[str, str] = {}
    if isinstance(node, dict):
        if isinstance(node.get("value"), str) and HEX_COLOR_RE.match(node["value"].strip()):
            values[prefix] = node["value"].strip()
            return values
        for key, value in node.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            values.update(_flatten_tokens(value, child_prefix))
    return values


def _normalize_ref(value: str) -> str:
    normalized = (value or "").strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        normalized = normalized[1:-1].strip()
    if normalized.startswith("$"):
        normalized = normalized[1:]
    return normalized


def _resolve_color(value: str, token_values: Dict[str, str]) -> Tuple[str, str]:
    normalized = _normalize_ref(value)
    if HEX_COLOR_RE.match(normalized):
        return normalized.lower(), normalized
    resolved = token_values.get(normalized, "")
    return resolved.lower(), normalized


def _snippet(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True)


def _line_col(text: str, needle: str) -> Tuple[int, int]:
    if not needle:
        return 1, 1
    index = text.find(needle)
    if index < 0:
        return 1, 1
    line = text.count("\n", 0, index) + 1
    last_newline = text.rfind("\n", 0, index)
    col = index - last_newline if last_newline >= 0 else index + 1
    return line, col


def _find_location(text: str, entry: dict, fallbacks: List[str]) -> Tuple[int, int]:
    for key in ("id", "token", "foreground", "background", "name", "meaning"):
        value = entry.get(key)
        if isinstance(value, str):
            line, col = _line_col(text, value)
            if (line, col) != (1, 1) or value in text:
                return line, col
    for fallback in fallbacks:
        line, col = _line_col(text, fallback)
        if (line, col) != (1, 1) or fallback in text:
            return line, col
    return 1, 1


def _blast_radius(entry: dict, default_file: str) -> dict:
    scope = str(entry.get("scope", "file") or "file").strip().lower()
    scope = scope if scope in {"component", "file", "design-system"} else "file"
    if scope == "component":
        label = entry.get("component") or entry.get("name") or "component"
        summary = f"one component ({label})"
    elif scope == "design-system":
        summary = "design-system wide"
    else:
        label = entry.get("file") or default_file
        summary = f"one file ({label})"
    return {"scope": scope, "summary": summary}


def _contrast_wcag(kind: str) -> str:
    return "1.4.11" if kind in {"ui", "focus"} else "1.4.3"


def _contrast_threshold(kind: str) -> float:
    mapping = {
        "text": 4.5,
        "large-text": 3.0,
        "ui": 3.0,
        "focus": 3.0,
    }
    return mapping.get(kind, 4.5)


def _contrast_issue(path: Path, text: str, token_values: Dict[str, str], entry: dict) -> Optional[dict]:
    fg_raw = entry.get("foreground") or entry.get("fg") or ""
    bg_raw = entry.get("background") or entry.get("bg") or ""
    fg_color, fg_ref = _resolve_color(fg_raw, token_values)
    bg_color, bg_ref = _resolve_color(bg_raw, token_values)
    if not fg_color or not bg_color:
        return None

    kind = str(entry.get("kind", "text") or "text").strip().lower()
    threshold = _contrast_threshold(kind)
    ratio = contrast_ratio(fg_color, bg_color)
    if ratio >= threshold:
        return None

    suggestion = suggest_alternative(fg_color, bg_color, threshold)
    line, col = _find_location(text, entry, [fg_ref, bg_ref])
    blast_radius = _blast_radius(entry, path.name)
    pair_id = entry.get("id") or f"{fg_ref}-on-{bg_ref}"
    message = (
        f"Token pair {pair_id} resolves to {fg_color} on {bg_color} at {ratio:.2f}:1, "
        f"below the required {threshold:.1f}:1 for {kind} contrast. "
        f"Blast radius: {blast_radius['summary']}."
    )
    if suggestion:
        message += f" Nearby compliant foreground: {suggestion}."

    return {
        "rule_id": "token-low-contrast",
        "wcag": _contrast_wcag(kind),
        "file": str(path),
        "line": line,
        "col": col,
        "snippet": _snippet(entry),
        "message": message,
        "framework": "token",
        "scanner": "token",
        "triage_hint": "input",
        "fix_data": {
            "pair_id": pair_id,
            "foreground_token": fg_ref,
            "background_token": bg_ref,
            "foreground_color": fg_color,
            "background_color": bg_color,
            "contrast_ratio": round(ratio, 2),
            "required_ratio": threshold,
            "suggested_color": suggestion or "",
            "kind": kind,
            "blast_radius": blast_radius,
            "token_name": pair_id,
        },
    }


def _focus_issue(path: Path, text: str, token_values: Dict[str, str], entry: dict) -> Optional[dict]:
    token_raw = entry.get("token") or entry.get("ring") or ""
    ring_color, token_ref = _resolve_color(token_raw, token_values)
    bg_raw = entry.get("background") or entry.get("surface") or ""
    bg_color, bg_ref = _resolve_color(bg_raw, token_values)
    width = entry.get("width_px", entry.get("width"))
    width_value = float(width) if isinstance(width, (int, float)) else None

    reasons = []
    ratio = None
    suggestion = ""
    if not ring_color:
        reasons.append("missing a resolvable focus-ring color token")
    elif bg_color:
        ratio = contrast_ratio(ring_color, bg_color)
        if ratio < 3.0:
            reasons.append(f"focus-ring contrast is {ratio:.2f}:1, below 3.0:1")
            suggestion = suggest_alternative(ring_color, bg_color, 3.0) or ""
    if width_value is not None and width_value < 2:
        reasons.append(f"focus-ring width is {width_value:g}px, below 2px")

    if not reasons:
        return None

    line, col = _find_location(text, entry, [token_ref, bg_ref])
    blast_radius = _blast_radius(entry, path.name)
    focus_id = entry.get("id") or token_ref or "focus-indicator"
    message = (
        f"Focus indicator token {focus_id} is insufficient because "
        + "; ".join(reasons)
        + f". Blast radius: {blast_radius['summary']}."
    )
    if suggestion:
        message += f" Nearby compliant ring color: {suggestion}."

    return {
        "rule_id": "token-focus-indicator",
        "wcag": "1.4.11",
        "file": str(path),
        "line": line,
        "col": col,
        "snippet": _snippet(entry),
        "message": message,
        "framework": "token",
        "scanner": "token",
        "triage_hint": "input",
        "fix_data": {
            "token_name": focus_id,
            "focus_token": token_ref,
            "background_token": bg_ref,
            "focus_color": ring_color,
            "background_color": bg_color,
            "contrast_ratio": round(ratio, 2) if ratio is not None else 0,
            "required_ratio": 3.0,
            "width_px": width_value if width_value is not None else 0,
            "suggested_color": suggestion,
            "blast_radius": blast_radius,
        },
    }


def _semantic_issue(path: Path, text: str, token_values: Dict[str, str], entry: dict) -> Optional[dict]:
    if entry.get("non_color_cue") is True:
        return None

    token_raw = entry.get("token") or entry.get("name") or ""
    color_value, token_ref = _resolve_color(token_raw, token_values)
    if not color_value:
        color_value = str(entry.get("value", "")).strip().lower()
        token_ref = token_ref or token_raw or str(entry.get("name", "")).strip()
    if not color_value:
        return None

    meaning = str(entry.get("meaning", token_ref or "state")).strip() or "state"
    line, col = _find_location(text, entry, [token_ref, meaning])
    blast_radius = _blast_radius(entry, path.name)
    semantic_id = entry.get("id") or token_ref or meaning
    message = (
        f"Semantic token {semantic_id} communicates {meaning} using color alone. "
        f"Provide a paired non-color cue such as text, iconography, or shape. "
        f"Blast radius: {blast_radius['summary']}."
    )

    return {
        "rule_id": "token-color-only-semantic",
        "wcag": "1.4.1",
        "file": str(path),
        "line": line,
        "col": col,
        "snippet": _snippet(entry),
        "message": message,
        "framework": "token",
        "scanner": "token",
        "triage_hint": "input",
        "fix_data": {
            "token_name": semantic_id,
            "semantic_token": token_ref,
            "semantic_color": color_value,
            "meaning": meaning,
            "blast_radius": blast_radius,
        },
    }


def analyze_tokens(path: Path) -> dict:
    data = _load_json(path)
    text = path.read_text(encoding="utf-8")
    token_root = data.get("tokens", data)
    token_values = _flatten_tokens(token_root)

    issues: List[dict] = []
    for entry in data.get("pairs", []):
        if isinstance(entry, dict):
            issue = _contrast_issue(path, text, token_values, entry)
            if issue:
                issues.append(issue)

    for entry in data.get("focus_indicators", []):
        if isinstance(entry, dict):
            issue = _focus_issue(path, text, token_values, entry)
            if issue:
                issues.append(issue)

    semantic_entries = data.get("semantic_states", data.get("semantic_tokens", []))
    for entry in semantic_entries:
        if isinstance(entry, dict):
            issue = _semantic_issue(path, text, token_values, entry)
            if issue:
                issues.append(issue)

    return {
        "scanner": "token",
        "source_format": "json-token-v1",
        "target": str(path),
        "files_scanned": 1,
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Accessibility design-token scanner")
    parser.add_argument("path", help="Path to a supported token JSON file")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 2

    try:
        report = analyze_tokens(path)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
