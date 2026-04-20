# Accessibility Audit Report

**Date**: <DATE>

Found **1** active findings: **1** safe to fix now, **0** need your decision. Also generated **6** guided checks for this target.

## Snapshot
- Target: fixtures/waiver-expired
- Framework: html
- Standard: WCAG 2.2 Level AA
- Mode: triage
- Checked: static
- Findings by source: static 1
- Baseline: none
- Confidence: high 1
Artifacts:
- `triage-report.json`

## What to do next
- **Safe to fix now (1):** say "apply the safe fixes" and the agent will patch them.
- **Test it yourself:** say "give me the checklist" — 6 guided checks for this target.
- **Baseline:** say "save the baseline" to make this run the new reference.


---

## Safe to fix now (1)

_The agent can apply these without further input. Say "apply the safe fixes" to proceed, or list which to skip._

### 1. [WCAG best-practice] — target="_blank" without rel="noopener"
**Location**: `fixtures/waiver-expired/index.html:9`
**Issue**: target="_blank" without rel="noopener noreferrer". Security and sometimes accessibility issue.
**Fix**:
```diff
- <a href="https://example.com" target="_blank" rel="external">Docs</a>
+ <a href="https://example.com" target="_blank" rel="external noopener noreferrer">Docs</a>
```

---

## Test it yourself

_These require a human in the browser or with assistive tech — the things automated scanners can't reliably check._

### Guided checklist (6)

#### 1. Keyboard tab order through the audited page or flow
**Capability**: `keyboard`
**WCAG**: 2.1.1, 2.4.3
**Context**: Use the current page-load state and every audited interaction state.
**How to test**:
- [ ] Press Tab from the browser chrome into the page and keep tabbing until focus returns to the browser or the end of the flow.
- [ ] Repeat with Shift+Tab to verify the reverse order.
**Expected result**:
- [ ] Every interactive element is reachable in a logical visual order.
- [ ] No keyboard trap appears and focus never jumps to hidden or inert UI.

#### 2. Focus visibility and focus return behavior
**Capability**: `visual`
**WCAG**: 2.4.7, 2.4.11
**Context**: Check each interactive state reached during the audit.
**How to test**:
- [ ] Tab to each control, including links, buttons, fields, and custom widgets.
- [ ] Trigger any overlays, menus, or popovers that appear in the audited flow and then close them.
**Expected result**:
- [ ] The active element has a visible focus indicator with sufficient contrast.
- [ ] When transient UI closes, focus returns to a sensible trigger or next logical control.

#### 3. Heading outline and page title announcement
**Capability**: `screen reader`
**WCAG**: 1.3.1, 2.4.2, 2.4.6
**Context**: Inspect the current page and any post-interaction destination states.
**How to test**:
- [ ] Open the page or flow with a screen reader rotor/list-of-headings view.
- [ ] Move by heading level and confirm the document title after each destination change.
**Expected result**:
- [ ] The title uniquely identifies the current page or state.
- [ ] Heading levels form a logical outline without skipped or decorative headings being announced as structure.

#### 4. Zoom, reflow, and text spacing resilience
**Capability**: `browser`
**WCAG**: 1.4.10, 1.4.12
**Context**: Run this on the main page and any key post-interaction view.
**How to test**:
- [ ] Check the page at 200% zoom and then at 320px CSS width.
- [ ] Override text spacing to line-height 1.5, paragraph spacing 2x, letter spacing 0.12em, and word spacing 0.16em.
**Expected result**:
- [ ] Content remains usable without horizontal scrolling for main reading content.
- [ ] No clipping, overlap, or lost controls appear when text spacing is increased.

#### 5. Reduced motion and motion-triggered interactions
**Capability**: `visual`
**WCAG**: 2.3.*
**Context**: Repeat the audited journey with reduced motion enabled if the UI animates.
**How to test**:
- [ ] Turn on the OS or browser reduced-motion preference and replay the audited flow.
- [ ] Trigger any animated transitions, expanding sections, or route changes observed during the scan.
**Expected result**:
- [ ] Non-essential motion is reduced or removed.
- [ ] Animations do not block task completion or hide focus movement.

#### 6. Use-of-color-only communication
**Capability**: `visual`
**WCAG**: 1.4.1
**Context**: Check interactive controls, validation states, charts, and inline status messages.
**How to test**:
- [ ] Review the page in grayscale or with color filters disabled.
- [ ] Inspect success, error, selected, and required states across the audited flow.
**Expected result**:
- [ ] Meaning is still clear without color perception.
- [ ] Status and selection are conveyed with text, iconography, or structural cues in addition to color.

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