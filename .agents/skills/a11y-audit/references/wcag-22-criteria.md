# WCAG 2.2 Criteria — Scanner Coverage

This table shows which WCAG 2.2 Level A and AA success criteria the skill's scanners check, and which rely on the manual checklist.

Legend:
- `static` — caught by `a11y_scan.py` (source file analysis)
- `runtime` — caught by `a11y_runtime.js` (axe-core on rendered DOM)
- `manual` — appears in the manual checklist; requires human testing

## Level A

| Criterion | What it requires | Coverage |
| --- | --- | --- |
| 1.1.1 Non-text Content | Text alternatives for images | static, runtime |
| 1.2.1–1.2.3 Time-based Media | Captions, audio descriptions, transcripts | — (manual; out of scope for automation) |
| 1.3.1 Info and Relationships | Structure conveyed programmatically | static (form labels, heading skips), runtime |
| 1.3.2 Meaningful Sequence | Reading order preserved | manual |
| 1.3.3 Sensory Characteristics | Instructions don't rely on shape/color alone | manual |
| 1.4.1 Use of Color | Color is not the only visual means | manual |
| 1.4.2 Audio Control | Audio ≥3s has pause/stop controls | static (flags autoplay) |
| 2.1.1 Keyboard | All functionality available via keyboard | static (clickable div/span), manual |
| 2.1.2 No Keyboard Trap | Can Tab away from any component | manual |
| 2.1.4 Character Key Shortcuts | Can be turned off or remapped | manual |
| 2.2.1 Timing Adjustable | Timeouts adjustable | manual |
| 2.2.2 Pause, Stop, Hide | Moving content controllable | manual |
| 2.3.1 Three Flashes or Below | No flashing >3× per second | manual |
| 2.4.1 Bypass Blocks | Skip link or landmarks | runtime (landmark checks), manual |
| 2.4.2 Page Titled | Pages have titles | runtime |
| 2.4.3 Focus Order | Focus order logical | static (positive tabindex), manual |
| 2.4.4 Link Purpose (In Context) | Link text makes sense | runtime (generic link text), manual |
| 2.5.1 Pointer Gestures | Multi-point gestures have single-point alternative | manual |
| 2.5.2 Pointer Cancellation | No unintended activation | manual |
| 2.5.3 Label in Name | Accessible name contains visible label | runtime |
| 2.5.4 Motion Actuation | Motion-triggered actions have alternatives | manual |
| 3.1.1 Language of Page | `<html lang>` set | static, runtime |
| 3.2.1 On Focus | Focus doesn't trigger context change | manual |
| 3.2.2 On Input | Input doesn't trigger context change | manual |
| 3.2.6 Consistent Help | Help in consistent location | manual |
| 3.3.1 Error Identification | Errors identified in text | runtime (partial), manual |
| 3.3.2 Labels or Instructions | Inputs have labels | static, runtime |
| 3.3.7 Redundant Entry (NEW 2.2) | Don't ask for same info twice | manual |
| 4.1.1 Parsing | Valid, parseable markup | runtime (duplicate ids) |
| 4.1.2 Name, Role, Value | Interactive elements have accessible name and role | static (redundant roles, aria-hidden), runtime |

## Level AA

| Criterion | What it requires | Coverage |
| --- | --- | --- |
| 1.2.4 Captions (Live) | Live captions for audio | — (manual) |
| 1.2.5 Audio Description | Video has audio description | — (manual) |
| 1.3.4 Orientation | Works in both orientations | manual |
| 1.3.5 Identify Input Purpose | `autocomplete` on common inputs | static (partial) |
| 1.4.3 Contrast (Minimum) | Text 4.5:1, large text 3:1 | static (partial — hex and Tailwind), runtime (full) |
| 1.4.4 Resize Text | Text resizable to 200% | manual |
| 1.4.5 Images of Text | Avoid images of text | manual |
| 1.4.10 Reflow | No horizontal scroll at 320px | manual |
| 1.4.11 Non-text Contrast | UI components 3:1 | runtime |
| 1.4.12 Text Spacing | Overrides don't clip content | manual |
| 1.4.13 Content on Hover/Focus | Dismissable, hoverable, persistent | manual |
| 2.4.5 Multiple Ways | Multiple ways to find pages | manual |
| 2.4.6 Headings and Labels | Descriptive headings and labels | runtime (partial), manual |
| 2.4.7 Focus Visible | Focus indicator visible | static (outline: none), manual |
| 2.4.11 Focus Appearance (NEW 2.2) | Focus indicator ≥2px, ≥3:1 contrast | static (outline: none), manual |
| 2.5.7 Dragging Movements (NEW 2.2) | Drag has single-pointer alternative | manual |
| 2.5.8 Target Size (NEW 2.2) | Interactive targets ≥24×24px | static (partial), runtime |
| 3.1.2 Language of Parts | Language changes marked | manual |
| 3.2.3 Consistent Navigation | Nav consistent across pages | manual |
| 3.2.4 Consistent Identification | Same function same name | manual |
| 3.3.3 Error Suggestion | Errors suggest fixes | manual |
| 3.3.4 Error Prevention | Legal/financial/data changes reviewable | manual |
| 3.3.8 Accessible Authentication (NEW 2.2) | No cognitive function tests without alternatives | manual |
| 4.1.3 Status Messages | Status announced without focus | runtime (partial), manual |

## Coverage summary

Roughly a third of Level A+AA success criteria are fully or partly automated. The rest live in the manual checklist. This matches the general consensus that automated tools catch ~30–40% of accessibility issues — figures reported by WebAIM, Deque, and others, though the exact percentage depends on how you count. The skill reports its findings honestly as a partial audit, not as compliance certification.
