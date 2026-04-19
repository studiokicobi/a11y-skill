# WCAG 2.2 Coverage Matrix

This file is the fixed coverage source for deterministic `not_checked`
population in triage output.

Coverage values:
- `static`
- `runtime`
- `stateful`
- `manual-template`
- `out-of-scope`

| Criterion | Title | Coverage | Notes |
| --- | --- | --- | --- |
| 1.1.1 | Non-text Content | static | Runtime also contributes, but static is the primary declared lane. |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | out-of-scope | Media asset review required. |
| 1.2.2 | Captions (Prerecorded) | out-of-scope | Media asset review required. |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | out-of-scope | Media asset review required. |
| 1.2.4 | Captions (Live) | out-of-scope | Live media review required. |
| 1.2.5 | Audio Description (Prerecorded) | out-of-scope | Media asset review required. |
| 1.3.1 | Info and Relationships | static | Runtime also contributes. |
| 1.3.2 | Meaningful Sequence | manual-template | Covered by the manual checklist. |
| 1.3.3 | Sensory Characteristics | manual-template | Covered by the manual checklist. |
| 1.3.4 | Orientation | manual-template | Covered by the manual checklist. |
| 1.3.5 | Identify Input Purpose | static | Partial static coverage only. |
| 1.4.1 | Use of Color | manual-template | Covered by the manual checklist. |
| 1.4.2 | Audio Control | out-of-scope | Static autoplay checks are partial and do not verify controls. |
| 1.4.3 | Contrast (Minimum) | runtime | Static contributes partial hints; runtime is the primary declared lane. |
| 1.4.4 | Resize Text | manual-template | Covered by the manual checklist. |
| 1.4.5 | Images of Text | manual-template | Covered by the manual checklist. |
| 1.4.10 | Reflow | manual-template | Covered by the manual checklist. |
| 1.4.11 | Non-text Contrast | runtime | Manual checklist also contributes. |
| 1.4.12 | Text Spacing | manual-template | Covered by the manual checklist. |
| 1.4.13 | Content on Hover or Focus | manual-template | Covered by the manual checklist. |
| 2.1.1 | Keyboard | static | Manual checklist also contributes. |
| 2.1.2 | No Keyboard Trap | manual-template | Covered by the manual checklist. |
| 2.1.4 | Character Key Shortcuts | manual-template | Covered by the manual checklist. |
| 2.2.1 | Timing Adjustable | out-of-scope | Flow and session review required. |
| 2.2.2 | Pause, Stop, Hide | out-of-scope | Flow and motion review required. |
| 2.3.1 | Three Flashes or Below Threshold | out-of-scope | Visual review required. |
| 2.4.1 | Bypass Blocks | runtime | Manual checklist also contributes. |
| 2.4.2 | Page Titled | runtime |  |
| 2.4.3 | Focus Order | manual-template | Static positive-tabindex detection is partial; manual review is the declared lane. |
| 2.4.4 | Link Purpose (In Context) | runtime | Manual checklist also contributes. |
| 2.4.5 | Multiple Ways | manual-template | Covered by the manual checklist. |
| 2.4.6 | Headings and Labels | runtime | Manual checklist also contributes. |
| 2.4.7 | Focus Visible | manual-template | Static outline removal checks are partial; manual review is the declared lane. |
| 2.4.11 | Focus Appearance | manual-template | Static outline removal checks are partial; manual review is the declared lane. |
| 2.5.1 | Pointer Gestures | manual-template | Covered by the manual checklist. |
| 2.5.2 | Pointer Cancellation | manual-template | Covered by the manual checklist. |
| 2.5.3 | Label in Name | runtime |  |
| 2.5.4 | Motion Actuation | manual-template | Covered by the manual checklist. |
| 2.5.7 | Dragging Movements | manual-template | Covered by the manual checklist. |
| 2.5.8 | Target Size (Minimum) | runtime | Static contributes partial hints. |
| 3.1.1 | Language of Page | static | Runtime also contributes. |
| 3.1.2 | Language of Parts | manual-template | Covered by the manual checklist. |
| 3.2.1 | On Focus | manual-template | Covered by the manual checklist. |
| 3.2.2 | On Input | manual-template | Covered by the manual checklist. |
| 3.2.3 | Consistent Navigation | manual-template | Covered by the manual checklist. |
| 3.2.4 | Consistent Identification | manual-template | Covered by the manual checklist. |
| 3.2.6 | Consistent Help | manual-template | Covered by the manual checklist. |
| 3.3.1 | Error Identification | manual-template | Runtime is partial; manual review is the declared lane. |
| 3.3.2 | Labels or Instructions | static | Runtime also contributes. |
| 3.3.3 | Error Suggestion | manual-template | Covered by the manual checklist. |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | manual-template | Covered by the manual checklist. |
| 3.3.7 | Redundant Entry | manual-template | Covered by the manual checklist. |
| 3.3.8 | Accessible Authentication (Minimum) | manual-template | Covered by the manual checklist. |
| 4.1.1 | Parsing | runtime |  |
| 4.1.2 | Name, Role, Value | runtime | Static contributes partial checks. |
| 4.1.3 | Status Messages | runtime | Manual checklist also contributes. |
