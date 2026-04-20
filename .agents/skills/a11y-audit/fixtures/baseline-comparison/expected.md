# Accessibility Audit Report

**Date**: <DATE>

Found **2** active findings: **0** safe to fix now, **2** need your decision. Also generated **7** guided checks for this target.

## Snapshot
- Target: fixtures/baseline-comparison
- Framework: html
- Standard: WCAG 2.2 Level AA
- Mode: triage
- Checked: static
- Findings by source: static 2
- Baseline: new 1, unchanged 1, fixed 1, resolved 1, waived 1
- Confidence: high 2
Artifacts:
- `triage-report.json`

## What to do next
- **Needs your decision (2):** say "walk me through the decisions" to answer them one at a time.
- **Test it yourself:** say "give me the checklist" — 7 guided checks for this target.
- **Baseline:** say "save the baseline" to make this run the new reference, or "update the baseline" to refresh the existing one.

Tracked statuses: waived 1, fixed 1, resolved 1.
Regression summary: new 1, unchanged 1, fixed 1, resolved 1, waived 1.

---

## Needs your decision (2)

_Each item asks one question. Say "walk me through the decisions" and the agent will go one at a time._

### 1. [WCAG 1.3.1] — Input missing label
**Location**: `fixtures/baseline-comparison/index.html:15`
**Baseline**: new
**Issue**: <input> has no associated <label> and no aria-label.
**Decision needed**: What should this input be labeled?
**Current code**:
```
<input name="email">
```

### 2. [WCAG 2.4.3] — Positive tabindex disrupts tab order
**Location**: `fixtures/baseline-comparison/index.html:11`
**Baseline**: unchanged
**Issue**: tabindex="5" breaks natural tab order. Nearly always should be 0 or removed.
**Decision needed**: Is this tab order deliberate? If not, we'll remove the positive tabindex.
**Current code**:
```
<button id="save-btn" tabindex="5">Save</button>
```

---

## Test it yourself

_These require a human in the browser or with assistive tech — the things automated scanners can't reliably check._

### Guided checklist (7)

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

#### 7. Form labels, errors, and required-state announcements
**Capability**: `screen reader`
**WCAG**: 3.3.1, 3.3.2, 4.1.2, 4.1.3
**Context**: Use the form states reached in the audited flow, including invalid submissions.
**How to test**:
- [ ] Move through each field with a screen reader and listen for label, role, value, and required state.
- [ ] Submit the form with missing or invalid data and listen for the first announced error.
**Expected result**:
- [ ] Every field announces a clear programmatic label and required status.
- [ ] Errors are announced in text, associated to the affected field, and do not rely on color alone.

---

## Waived (skipped on purpose) (1)

### 1. [WCAG 1.1.1] — Image missing alt attribute
**Location**: `fixtures/baseline-comparison/index.html:6`
**Baseline**: waived
**Reason**: Marketing is replacing the hero asset in the next content push.
**Approved by**: a11y-lead
**Expires**: 2026-12-31T00:00:00Z

---

## Resolved & tracked (2)

These findings were carried from status records and are kept for tracking, not active remediation:

### 1. [WCAG 2.1.1] — Non-interactive element with click handler
**Location**: `fixtures/baseline-comparison/index.html:8`
**Status**: fixed
**Baseline**: fixed
**Reason**: Rule is classified as safe to patch automatically for this evidence source.

### 2. [WCAG best-practice] — target="_blank" without rel="noopener"
**Location**: `fixtures/baseline-comparison/index.html:10`
**Status**: resolved
**Baseline**: resolved
**Reason**: Finding status is resolved; it is tracked for reporting but not surfaced in active remediation groups.

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