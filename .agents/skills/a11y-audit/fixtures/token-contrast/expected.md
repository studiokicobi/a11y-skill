# Accessibility Audit Report

**Date**: <DATE>

Found **1** active findings: **0** safe to fix now, **1** need your decision. Also generated **3** guided checks for this target.

## Snapshot
- Target: fixtures/token-contrast/tokens.json
- Framework: token
- Standard: WCAG 2.2 Level AA
- Mode: triage
- Checked: token
- Findings by source: token 1
- Baseline: none
- Confidence: high 1
Artifacts:
- `triage-report.json`

## What to do next
- **Needs your decision (1):** say "walk me through the decisions" to answer them one at a time.
- **Test it yourself:** say "give me the checklist" — 3 guided checks for this target.
- **Baseline:** say "save the baseline" to make this run the new reference.


---

## Needs your decision (1)

_Each item asks one question. Say "walk me through the decisions" and the agent will go one at a time._

### 1. [WCAG 1.4.3] — Token contrast pair fails WCAG
**Location**: `fixtures/token-contrast/tokens.json:18`
**Blast radius**: design-system wide
**Issue**: Token pair body-muted resolves to #9aa0aa on #ffffff at 2.63:1, below the required 4.5:1 for text contrast. Blast radius: design-system wide. Nearby compliant foreground: #717781.
**Decision needed**: Which nearby compliant token value should replace this failing pair?
**Current code**:
```
{"background": "color.surface.default", "foreground": "color.text.muted", "id": "body-muted", "kind": "text", "scope": "design-system"}
```

---

## Test it yourself

_These require a human in the browser or with assistive tech — the things automated scanners can't reliably check._

### Guided checklist (3)

#### 1. Use-of-color-only communication across semantic tokens
**Capability**: `visual`
**WCAG**: 1.4.1
**Context**: Inspect tokens that convey meaning (success, error, warning, info, selected, disabled).
**How to test**:
- [ ] Preview each semantic token pair in a color-blindness simulator or grayscale.
- [ ] Check that the paired icon, label, or shape token is mandatory (not optional) in the component spec.
**Expected result**:
- [ ] Meaning survives without hue perception.
- [ ] The design system documents the non-color companion cue for every semantic state.

#### 2. Theme coverage for every semantic token
**Capability**: `design system`
**WCAG**: 1.4.3, 1.4.11
**Context**: If the product supports multiple themes (light/dark, high-contrast, branded), each semantic token needs a value in every theme.
**How to test**:
- [ ] Open the token source and confirm each semantic token has a value in every supported theme.
- [ ] Spot-check contrast pairs in each theme with the contrast checker.
**Expected result**:
- [ ] No token resolves to `undefined` or inherits an inappropriate parent value in any theme.
- [ ] Each theme passes the contrast rules the default theme passes.

#### 3. Rendered composition at component boundaries
**Capability**: `visual`
**WCAG**: 1.4.3, 1.4.11
**Context**: The token scan checks declared token pairs. It cannot see how components compose them (e.g., disabled text on a disabled background, tooltip on a translucent overlay).
**How to test**:
- [ ] List the component states that combine multiple tokens (disabled, hover, focus, selected, overlay).
- [ ] Render each combination and measure the effective contrast against the background it actually lands on.
**Expected result**:
- [ ] Every rendered combination meets the relevant contrast ratio.
- [ ] Tokens that only pass in isolation are flagged in the design system as 'do not combine with X'.

---

## Not checked by this audit

These WCAG criteria are outside what the scanners can evaluate. The audit above is incomplete without addressing these separately:
- 1.2.1 — Audio-only and Video-only (Prerecorded) — Media asset review required.
- 1.2.2 — Captions (Prerecorded) — Media asset review required.
- 1.2.3 — Audio Description or Media Alternative (Prerecorded) — Media asset review required.
- 1.2.4 — Captions (Live) — Live media review required.
- 1.2.5 — Audio Description (Prerecorded) — Media asset review required.
- 1.3.2 — Meaningful Sequence — The checklist exercises tab order (2.4.3); programmatic reading-sequence review is not automated.
- 1.3.3 — Sensory Characteristics — Non-color sensory cues (shape, size, orientation, sound) are not exercised by the checklist.
- 1.3.4 — Orientation — Portrait/landscape lock review not automated; 1.4.10 reflow is separate.
- 1.3.5 — Identify Input Purpose — No autocomplete rule is implemented; user must review `autocomplete` attributes on personal-data fields.
- 1.4.13 — Content on Hover or Focus — Hoverable/focusable revealed content (tooltips, popovers) is not exercised by the checklist.
- 1.4.5 — Images of Text — Image-of-text detection is not automated; the checklist doesn't exercise it.
- 2.1.4 — Character Key Shortcuts — Single-character shortcuts are not audited automatically.
- 2.2.1 — Timing Adjustable — Session-timeout review required.
- 2.2.2 — Pause, Stop, Hide — Auto-updating content review required.
- 2.3.1 — Three Flashes or Below Threshold — Flashing/seizure review requires a visual frame-rate pass the scanner cannot perform.
- 2.4.5 — Multiple Ways — Multi-path navigation (search, sitemap, nav) review is not automated and the checklist doesn't exercise it.
- 2.5.1 — Pointer Gestures — Multi-point / path-based gestures (pinch, rotate, swipe paths) are not exercised by the checklist; 2.5.7 dragging is covered separately.
- 2.5.2 — Pointer Cancellation — Down-event / up-event behavior is not audited automatically.
- 2.5.4 — Motion Actuation — Device-motion / user-motion triggers are not audited automatically.
- 3.1.2 — Language of Parts — Inline `lang` attributes on foreign-language passages are not audited automatically.
- 3.2.1 — On Focus — Context-change-on-focus review is not automated.
- 3.2.2 — On Input — Context-change-on-input review is not automated.
- 3.2.3 — Consistent Navigation — Cross-page consistency review is not in scope for a single audit run.
- 3.2.4 — Consistent Identification — Cross-page consistent labeling review is not in scope for a single audit run.
- 3.2.6 — Consistent Help — Cross-page consistent-help-location review is not in scope for a single audit run.
- 3.3.3 — Error Suggestion — Correction-suggestion review is not in scope; the checklist only confirms errors are announced.
- 3.3.4 — Error Prevention (Legal, Financial, Data) — Destructive-action confirmation review is not automated.
- 3.3.7 — Redundant Entry — Multi-step flow review required.
- 3.3.8 — Accessible Authentication (Minimum) — Auth flow review required.