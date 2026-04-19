# Accessibility Audit Report

**Target**: http://localhost:3000
**Framework**: unknown
**Standard**: WCAG 2.2 Level AA
**Date**: <DATE>

## Summary
Found 1 scanner-detected issues: **0 auto-fixable**, **1 need your input**, plus a manual checklist below. (0 scanner-flagged items require manual review.)
By source: runtime 1.
By confidence: high 1.

---

## Group 1: Auto-fixable (0 issues)

_None._

---

## Group 2: Needs your input (1 issues)

These need a decision from you. The agent can draft each fix once you answer.

### 1. [WCAG 1.4.3] — Color contrast failure (runtime)
**Location**: `http://localhost:3000`
**Issue**: Elements must meet minimum color contrast ratio thresholds
**Decision needed**: Pick an accessible color that aligns with your brand — we'll suggest 2–3 options if you want.
**Current code**:
```
<p class="muted-copy">Low contrast helper text</p>
```

---

## Group 3: Manual checklist

These require you to test with actual assistive technology or in the browser. Automated tools catch roughly a third of accessibility issues — the rest live here.

### Keyboard navigation (WCAG 2.1.1, 2.4.3, 2.4.7, 2.4.11)
- [ ] Tab through the full page — every interactive element is reachable
- [ ] Tab order follows visual/reading order, no unexpected jumps
- [ ] Every focused element has a clearly visible focus indicator (≥2px, ≥3:1 contrast)
- [ ] Shift+Tab works in reverse and matches the forward order
- [ ] No keyboard traps — you can always Tab out of any component
- [ ] Escape closes modals, popovers, dropdowns, and autocompletes
- [ ] Enter and Space activate buttons; Enter activates links
- [ ] Within composite widgets (tabs, menus, listboxes), arrow keys move within and Tab moves out
- [ ] Modals trap focus and return focus to the trigger element on close

### Screen reader (WCAG 1.3.1, 2.4.2, 2.4.6, 4.1.2, 4.1.3)
- [ ] Page title describes the current page uniquely
- [ ] Heading structure creates a logical outline when navigating by headings
- [ ] All form inputs announce label, required state, and any error
- [ ] Dynamic content changes (toasts, errors, loaded results) are announced
- [ ] Custom widgets announce role and state (expanded/collapsed, selected)
- [ ] Route changes in SPAs are announced
- [ ] Icon buttons announce their purpose, not the icon name

### Visual and motion (WCAG 1.4.1, 1.4.10, 1.4.11, 1.4.12, 2.3.*)
- [ ] Page usable at 200% zoom with no horizontal scroll at 1280px viewport
- [ ] Page reflows at 320px width without loss of content
- [ ] Text spacing can be overridden without clipping (line-height 1.5, paragraph 2×, letter 0.12em)
- [ ] No information conveyed by color alone (check with a grayscale filter)
- [ ] UI component borders/states meet 3:1 contrast against adjacent colors
- [ ] Animations respect `prefers-reduced-motion`
- [ ] No content flashes more than 3× per second

### Forms (WCAG 3.3.1–3.3.8)
- [ ] Errors identify the problem in text (not just color/icon)
- [ ] Required fields indicated in the label (not just with a red asterisk)
- [ ] Input type matches content (email, tel, etc.)
- [ ] Password fields allow paste
- [ ] CAPTCHA has a non-cognitive alternative (WCAG 2.2 — 3.3.8)
- [ ] Multi-step flows don't ask for re-entry of earlier data (WCAG 2.2 — 3.3.7)

---

## Not checked by this audit

These WCAG criteria are outside what the scanners can evaluate. The audit above is incomplete without addressing these separately:
- 1.2.1 — Audio-only and Video-only (Prerecorded) — Media asset review required.
- 1.2.2 — Captions (Prerecorded) — Media asset review required.
- 1.2.3 — Audio Description or Media Alternative (Prerecorded) — Media asset review required.
- 1.2.4 — Captions (Live) — Live media review required.
- 1.2.5 — Audio Description (Prerecorded) — Media asset review required.
- 1.4.2 — Audio Control — Static autoplay checks are partial and do not verify controls.
- 2.2.1 — Timing Adjustable — Flow and session review required.
- 2.2.2 — Pause, Stop, Hide — Flow and motion review required.
- 2.3.1 — Three Flashes or Below Threshold — Visual review required.
