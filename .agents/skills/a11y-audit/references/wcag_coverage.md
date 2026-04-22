# WCAG 2.2 Coverage Matrix

This file is the fixed coverage source for deterministic `not_checked`
population in triage output. Only rows with `coverage: out-of-scope` are
rendered in the report's "Not checked" section.

Coverage values:
- `static` — covered by `scripts/a11y_scan.py` (Python, no runtime)
- `runtime` — covered by axe-core via `scripts/a11y_runtime.js` / `scripts/a11y_stateful.js`
- `stateful` — covered specifically by the multi-step journey runner
- `manual-template` — rendered as an item in the Guided checklist (`generate_manual_review_items` in triage.py)
- `out-of-scope` — no scanner evaluates this; the user is told explicitly

Rules behind each `static` / `runtime` entry are listed in `references/triage-rules.md`. Keep that doc and this table in sync.

| Criterion | Title | Coverage | Notes |
| --- | --- | --- | --- |
| 1.1.1 | Non-text Content | static | `img-missing-alt` (static) + axe `image-alt` (runtime). |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | out-of-scope | Media asset review required. |
| 1.2.2 | Captions (Prerecorded) | out-of-scope | Media asset review required. |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | out-of-scope | Media asset review required. |
| 1.2.4 | Captions (Live) | out-of-scope | Live media review required. |
| 1.2.5 | Audio Description (Prerecorded) | out-of-scope | Media asset review required. |
| 1.3.1 | Info and Relationships | static | `input-missing-label`, `input-placeholder-as-label` (static) + axe `label`, `heading-order` (runtime). |
| 1.3.2 | Meaningful Sequence | out-of-scope | The checklist exercises tab order (2.4.3); programmatic reading-sequence review is not automated. |
| 1.3.3 | Sensory Characteristics | out-of-scope | Non-color sensory cues (shape, size, orientation, sound) are not exercised by the checklist. |
| 1.3.4 | Orientation | out-of-scope | Portrait/landscape lock review not automated; 1.4.10 reflow is separate. |
| 1.3.5 | Identify Input Purpose | out-of-scope | No autocomplete rule is implemented; user must review `autocomplete` attributes on personal-data fields. |
| 1.4.1 | Use of Color | manual-template | Token scanner flags `token-color-only-semantic`; Guided checklist covers rendered use-of-color. |
| 1.4.2 | Audio Control | static | `media-autoplay` flags `<audio>`/`<video>` with `autoplay`; the decision prompt asks whether to remove autoplay or add pause controls. Silent audio outside autoplayed media is not detected. |
| 1.4.3 | Contrast (Minimum) | runtime | axe `color-contrast` (runtime) + `tailwind-low-contrast`, `css-low-contrast`, `token-low-contrast` (static/token). |
| 1.4.4 | Resize Text | manual-template | Covered by the Guided checklist (200% zoom step in the zoom/reflow/text-spacing item). |
| 1.4.5 | Images of Text | out-of-scope | Image-of-text detection is not automated; the checklist doesn't exercise it. |
| 1.4.10 | Reflow | manual-template | Covered by the Guided checklist (320px CSS width step). |
| 1.4.11 | Non-text Contrast | runtime | axe `color-contrast` for UI components; Guided checklist also contributes. |
| 1.4.12 | Text Spacing | manual-template | Covered by the Guided checklist (text-spacing override step). |
| 1.4.13 | Content on Hover or Focus | out-of-scope | Hoverable/focusable revealed content (tooltips, popovers) is not exercised by the checklist. |
| 2.1.1 | Keyboard | static | `clickable-div` (static) + Guided checklist (full keyboard sweep). |
| 2.1.2 | No Keyboard Trap | manual-template | The checklist's overlay item runs when the audit touches an overlay; a general keyboard-trap sweep is the tester's responsibility during the tab-order walk. |
| 2.1.4 | Character Key Shortcuts | out-of-scope | Single-character shortcuts are not audited automatically. |
| 2.2.1 | Timing Adjustable | out-of-scope | Session-timeout review required. |
| 2.2.2 | Pause, Stop, Hide | out-of-scope | Auto-updating content review required. |
| 2.3.1 | Three Flashes or Below Threshold | out-of-scope | Flashing/seizure review requires a visual frame-rate pass the scanner cannot perform. |
| 2.3.3 | Animation from Interactions | manual-template | Covered by the Guided checklist's reduced-motion item (`prefers-reduced-motion` replay). |
| 2.4.1 | Bypass Blocks | runtime | axe `bypass` / `skip-link`. |
| 2.4.2 | Page Titled | runtime | axe `document-title`. |
| 2.4.3 | Focus Order | static | `positive-tabindex` (static) + axe `tabindex` (runtime) + Guided checklist for ordering. |
| 2.4.4 | Link Purpose (In Context) | runtime | axe `link-name` + Guided checklist. |
| 2.4.5 | Multiple Ways | out-of-scope | Multi-path navigation (search, sitemap, nav) review is not automated and the checklist doesn't exercise it. |
| 2.4.6 | Headings and Labels | runtime | axe `empty-heading`, `label-title-only` + Guided checklist (heading outline). |
| 2.4.7 | Focus Visible | static | `outline-none` (static) + Guided checklist (visible focus sweep). |
| 2.4.11 | Focus Appearance | static | `outline-none`, `token-focus-indicator` (static/token) + Guided checklist. |
| 2.5.1 | Pointer Gestures | out-of-scope | Multi-point / path-based gestures (pinch, rotate, swipe paths) are not exercised by the checklist; 2.5.7 dragging is covered separately. |
| 2.5.2 | Pointer Cancellation | out-of-scope | Down-event / up-event behavior is not audited automatically. |
| 2.5.3 | Label in Name | runtime | axe `label-content-name-mismatch`. |
| 2.5.4 | Motion Actuation | out-of-scope | Device-motion / user-motion triggers are not audited automatically. |
| 2.5.7 | Dragging Movements | manual-template | Covered by the Guided checklist. |
| 2.5.8 | Target Size (Minimum) | runtime | axe `target-size`. |
| 3.1.1 | Language of Page | static | `html-missing-lang` (static) + axe `html-has-lang` (runtime). |
| 3.1.2 | Language of Parts | out-of-scope | Inline `lang` attributes on foreign-language passages are not audited automatically. |
| 3.2.1 | On Focus | out-of-scope | Context-change-on-focus review is not automated. |
| 3.2.2 | On Input | out-of-scope | Context-change-on-input review is not automated. |
| 3.2.3 | Consistent Navigation | out-of-scope | Cross-page consistency review is not in scope for a single audit run. |
| 3.2.4 | Consistent Identification | out-of-scope | Cross-page consistent labeling review is not in scope for a single audit run. |
| 3.2.6 | Consistent Help | out-of-scope | Cross-page consistent-help-location review is not in scope for a single audit run. |
| 3.3.1 | Error Identification | manual-template | Covered by the Guided checklist's form-errors item (fires when the audit touches forms). |
| 3.3.2 | Labels or Instructions | static | `input-missing-label`, `input-placeholder-as-label` (static) + axe `label` (runtime). |
| 3.3.3 | Error Suggestion | out-of-scope | Correction-suggestion review is not in scope; the checklist only confirms errors are announced. |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | out-of-scope | Destructive-action confirmation review is not automated. |
| 3.3.7 | Redundant Entry | out-of-scope | Multi-step flow review required. |
| 3.3.8 | Accessible Authentication (Minimum) | out-of-scope | Auth flow review required. |
| 4.1.2 | Name, Role, Value | runtime | `redundant-role`, `icon-only-control`, `aria-hidden-focusable` (static) + axe `aria-*` (runtime). |
| 4.1.3 | Status Messages | runtime | axe `aria-live` checks + Guided checklist (live-region announcements). |

> **Note on 4.1.1 Parsing**: WCAG 2.2 removed this criterion as obsolete. The static `duplicate-id` rule still flags duplicate ids because they break `label[for]`, ARIA id-refs, and JS lookups — the finding maps to 4.1.1 for historical continuity but is not required for WCAG 2.2 AA conformance.
