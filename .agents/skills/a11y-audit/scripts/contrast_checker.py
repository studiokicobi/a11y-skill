#!/usr/bin/env python3
"""
contrast_checker.py — WCAG 2.2 color contrast validator.

Computes WCAG relative luminance contrast ratios. Supports:
- Single foreground/background pair check
- Scanning a CSS file for color declarations
- Suggesting accessible alternatives from a curated map

Usage:
    python contrast_checker.py --fg "#999" --bg "#fff"
    python contrast_checker.py --file path/to/styles.css
    python contrast_checker.py --fg "#666" --bg "#fff" --suggest

Exit codes:
    0 — all pairs pass (at chosen level)
    1 — one or more pairs fail
    2 — error (bad input)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple


# Minimum acceptable contrast ratios per WCAG 2.2.
THRESHOLDS = {
    "aa_normal": 4.5,
    "aa_large": 3.0,
    "aaa_normal": 7.0,
    "aaa_large": 4.5,
    "ui_component": 3.0,  # 1.4.11 Non-text Contrast
}


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    s = hex_color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError as e:
        raise ValueError(f"Invalid hex color: {hex_color}") from e


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def relative_luminance(rgb: Tuple[int, int, int]) -> float:
    # Per WCAG 2.2 definition.
    def channel(c: int) -> float:
        cs = c / 255.0
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    l1 = relative_luminance(hex_to_rgb(fg))
    l2 = relative_luminance(hex_to_rgb(bg))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def evaluate(fg: str, bg: str) -> dict:
    ratio = contrast_ratio(fg, bg)
    return {
        "fg": fg,
        "bg": bg,
        "ratio": round(ratio, 2),
        "aa_normal": ratio >= THRESHOLDS["aa_normal"],
        "aa_large": ratio >= THRESHOLDS["aa_large"],
        "aaa_normal": ratio >= THRESHOLDS["aaa_normal"],
        "ui_component": ratio >= THRESHOLDS["ui_component"],
    }


# Curated map of commonly-failing colors to accessible alternatives on white backgrounds.
# Each entry: original -> (replacement, ratio). Kept deliberately small; see
# references/contrast-alternatives.md for the full discussion.
ACCESSIBLE_ALTERNATIVES_ON_WHITE = {
    "#aaa": "#767676", "#aaaaaa": "#767676",
    "#bbb": "#767676", "#bbbbbb": "#767676",
    "#ccc": "#707070", "#cccccc": "#707070",
    "#999": "#767676", "#999999": "#767676",
    "#888": "#767676", "#888888": "#767676",
    "#777": "#757575", "#777777": "#757575",
}


def suggest_alternative(fg: str, bg: str, target_ratio: float = 4.5) -> Optional[str]:
    fg_norm = fg.lower()
    # If it's a known-bad value, return the curated answer
    if bg.lower() in {"#fff", "#ffffff"} and fg_norm in ACCESSIBLE_ALTERNATIVES_ON_WHITE:
        return ACCESSIBLE_ALTERNATIVES_ON_WHITE[fg_norm]
    # Otherwise, darken toward black until target ratio is met (for dark-on-light)
    # or lighten toward white (for light-on-dark). This is a reasonable fallback,
    # but won't always produce a brand-consistent result.
    try:
        r, g, b = hex_to_rgb(fg)
        bg_lum = relative_luminance(hex_to_rgb(bg))
    except ValueError:
        return None
    darken = bg_lum > 0.5  # bright background → darken foreground
    step = -1 if darken else 1
    best = None
    for _ in range(255):
        r = max(0, min(255, r + step))
        g = max(0, min(255, g + step))
        b = max(0, min(255, b + step))
        candidate = rgb_to_hex((r, g, b))
        if contrast_ratio(candidate, bg) >= target_ratio:
            best = candidate
            break
        if (r, g, b) in {(0, 0, 0), (255, 255, 255)}:
            break
    return best


COLOR_DECL_RE = re.compile(
    r"(color|background|background-color|border-color)\s*:\s*(#[0-9a-fA-F]{3,8})",
    re.IGNORECASE,
)


def scan_file(path: Path) -> list:
    """Pull out explicit color declarations. This is heuristic — CSS has many
    ways to define color, and this only catches hex values on named properties.
    For thorough analysis, use the runtime scanner on a rendered page."""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        for m in COLOR_DECL_RE.finditer(line):
            findings.append({
                "file": str(path),
                "line": line_no,
                "property": m.group(1),
                "value": m.group(2),
            })
    return findings


def main():
    parser = argparse.ArgumentParser(description="WCAG 2.2 color contrast checker.")
    parser.add_argument("--fg", type=str, help="Foreground color (hex)")
    parser.add_argument("--bg", type=str, help="Background color (hex)")
    parser.add_argument("--file", type=str, help="CSS file to scan for color declarations")
    parser.add_argument("--level", choices=["aa", "aaa"], default="aa")
    parser.add_argument("--large", action="store_true",
                        help="Treat text as large (≥24px or ≥18.66px bold)")
    parser.add_argument("--suggest", action="store_true",
                        help="Suggest an accessible alternative for failures")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.file:
        findings = scan_file(Path(args.file))
        out = {"file": args.file, "color_declarations": findings,
               "note": "This lists declarations only. Pair them with backgrounds using the runtime scanner for actual contrast ratios."}
        print(json.dumps(out, indent=2) if args.json else
              f"Found {len(findings)} color declarations in {args.file}. "
              f"Run the runtime scanner for computed contrast analysis.")
        return 0

    if not (args.fg and args.bg):
        parser.error("Provide --fg and --bg, or --file")

    try:
        result = evaluate(args.fg, args.bg)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    threshold_key = f"{args.level}_{'large' if args.large else 'normal'}"
    passes = result[threshold_key]

    if args.suggest and not passes:
        result["suggested_alternative"] = suggest_alternative(
            args.fg, args.bg, THRESHOLDS[threshold_key]
        )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Foreground: {args.fg}  Background: {args.bg}")
        print(f"Contrast ratio: {result['ratio']}:1")
        print(f"  AA normal (4.5:1):  {'PASS' if result['aa_normal'] else 'FAIL'}")
        print(f"  AA large  (3.0:1):  {'PASS' if result['aa_large'] else 'FAIL'}")
        print(f"  AAA normal (7.0:1): {'PASS' if result['aaa_normal'] else 'FAIL'}")
        if args.suggest and not passes:
            suggestion = result.get("suggested_alternative")
            if suggestion:
                new_ratio = contrast_ratio(suggestion, args.bg)
                print(f"\nSuggested alternative: {suggestion} "
                      f"({new_ratio:.2f}:1 against {args.bg})")
            else:
                print("\nNo safe alternative found; pick a manually-chosen color.")

    return 0 if passes else 1


if __name__ == "__main__":
    sys.exit(main())
