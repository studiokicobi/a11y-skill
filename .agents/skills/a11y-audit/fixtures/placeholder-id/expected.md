# Accessibility Audit Report

**Target**: fixtures/placeholder-id
**Framework**: html
**Standard**: WCAG 2.2 Level AA
**Date**: <DATE>

## Summary
Found 1 scanner-detected issues: **1 auto-fixable**, **0 need your input**, plus a manual checklist below. (0 scanner-flagged items require manual review.)
By source: static 1.
By confidence: high 1.

---

## Group 1: Auto-fixable (1 issues)

The agent can apply these fixes without further input. Reply **"go"** to proceed, or list which to skip.

### 1. [WCAG 1.3.1] — Placeholder used as only label
**Location**: `fixtures/placeholder-id/index.html:14`
**Issue**: <input> uses placeholder as only label. Placeholder disappears on input — add a visible <label>.
**Fix**:
```diff
- <input type="email" name="contact_email" placeholder="Email">
+ <label for="contact-email-14">Email</label>
+ <input type="email" name="contact_email" id="contact-email-14" placeholder="Email">
```

---

## Group 2: Needs your input (0 issues)

_None._

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
