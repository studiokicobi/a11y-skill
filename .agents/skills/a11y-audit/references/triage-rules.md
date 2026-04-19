# Triage Rules

Every detected violation gets classified into one of three groups. The rule is **what does the agent need from the user to fix it?**

- **Auto-fixable (Group 1)**: agent has everything it needs. One command applies the fix.
- **Needs human input (Group 2)**: agent knows *where* and *how*, but needs a content/copy/design decision.
- **Manual checklist (Group 3)**: automated tools can't verify this. User must test it.

When classifying a new violation that isn't in the tables below, apply the rule above and use judgement. When in doubt, prefer Group 2 over Group 1 — a wrong auto-fix is worse than a pending one.

---

## Group 1: Auto-fixable

These fixes have a deterministic correct output given what the scanner already knows.

| Rule | WCAG | Why auto-fixable |
| --- | --- | --- |
| `<div onClick>` or `<span onClick>` with no role | 2.1.1, 4.1.2 | Replace element with `<button type="button">` (or `<a href>` if it navigates and the href is clear from context) |
| Missing `type` on `<button>` inside a form | 4.1.2 | Default is `submit` which is often wrong. Add `type="button"` unless it's clearly the submit button |
| `<html>` missing `lang` attribute | 3.1.1 | Add `lang="en"` (or detect from `package.json` / existing content) |
| Redundant ARIA role (`<nav role="navigation">`, `<button role="button">`) | 4.1.2 | Remove the redundant attribute |
| `outline: none` or `outline: 0` on focusable elements with no `:focus-visible` replacement | 2.4.7, 2.4.11 | Add `:focus-visible { outline: 2px solid <accent>; outline-offset: 2px; }` using existing accent color from CSS vars or Tailwind config |
| `<img>` with `alt=""` that has a `title` or adjacent text that looks informational | 1.1.1 | Replace empty alt with the title/adjacent text content |
| `placeholder` used as only label on `<input>` | 1.3.1, 3.3.2 | Add a `<label for="...">` with the placeholder text; keep placeholder as example value |
| Heading skips (h1 → h3) where the h3 is the only heading at its level | 1.3.1 | Downgrade to h2 |
| Color contrast failure where the failing color is in `references/contrast-alternatives.md` | 1.4.3 | Replace with the mapped accessible alternative |
| Tailwind class like `text-gray-400` on a white/light background | 1.4.3 | Swap to the mapped accessible Tailwind class (see `contrast-alternatives.md`) |
| `<a href="#">` with no other handler | 2.1.1 | Replace with `<button type="button">` |
| `target="_blank"` without `rel="noopener noreferrer"` | best practice | Add `rel="noopener noreferrer"` |
| `aria-hidden="true"` on a focusable element | 4.1.2 | Remove `aria-hidden` OR add `tabindex="-1"` (prefer removal unless context clearly wants the element visually-only) |
| Form `<input>` missing `autocomplete` for common fields (email, name, tel, password) | 1.3.5 | Add the standard `autocomplete` value |
| Duplicate `id` attributes in the same document | 4.1.1 | Rename one to be unique |
| `role="presentation"` on an interactive element | 4.1.2 | Remove the role |
| Missing `<title>` in `<head>` or Next.js metadata | 2.4.2 | Add title based on route/filename; flag for review but apply |
| Click targets smaller than 24×24px on interactive elements with inline styles setting dimensions | 2.5.8 | Add `min-width: 24px; min-height: 24px` |

---

## Group 2: Needs human input

The agent can locate and structure the fix, but the *content* needs a human.

| Rule | WCAG | What the agent needs |
| --- | --- | --- |
| `<img>` missing `alt` attribute entirely (informational image) | 1.1.1 | **What does this image convey?** Agent proposes alt from filename/context, user confirms or edits |
| `<img>` where context can't determine decorative vs informational | 1.1.1 | **Is this decorative or informational?** If decorative → `alt=""`, if informational → user supplies alt text |
| `<input>` with no label and no nearby text hint | 1.3.1 | **What should this field be labeled?** Agent proposes from `name`/`id`, user confirms |
| Color contrast failure where no safe automatic mapping exists (brand colors, gradients, colors not in the alternatives map) | 1.4.3 | **Pick an accessible replacement.** Agent suggests 2–3 options that pass AA against the existing background |
| Link text is generic ("click here", "read more", "learn more") | 2.4.4 | **What does this link describe?** Agent proposes based on surrounding content, user confirms |
| Missing page `<title>` where no obvious source (unusual route, dynamic) | 2.4.2 | **What should this page be titled?** |
| Form error messages not associated with inputs and no pattern found | 3.3.1 | **Confirm: should errors appear inline below each field, or in a summary at the top?** Different patterns, different fixes |
| Modal/dialog missing accessible name | 4.1.2 | **What's the dialog's purpose?** (agent suggests `aria-label` from nearby heading if present) |
| Icon-only button missing accessible name | 4.1.2 | **What does this button do?** Proposes `aria-label` from icon name or surrounding context |
| Autoplay video/audio detected | 1.4.2 | **Keep autoplay? If so, confirm there's a pause control. Recommended: remove autoplay.** |
| `tabindex` value > 0 (breaks natural tab order) | 2.4.3 | **Is this ordering deliberate?** Nearly always should be `tabindex="0"` or removed — but requires confirmation |
| Language change within content not marked with `lang` | 3.1.2 | **Which sections are in which languages?** |

---

## Group 3: Manual checklist

Automated tools cannot verify these. The user must test in a browser with assistive technology.

### Keyboard navigation (WCAG 2.1.1, 2.1.2, 2.4.3, 2.4.7, 2.4.11)
- [ ] Tab through the full page — every interactive element is reachable
- [ ] Tab order follows visual/reading order, no unexpected jumps
- [ ] Every focused element has a clearly visible focus indicator (≥2px, ≥3:1 contrast)
- [ ] Shift+Tab works in reverse and matches the forward order
- [ ] No keyboard traps — you can always Tab out of any component
- [ ] Escape closes modals, popovers, dropdowns, and autocompletes
- [ ] Enter and Space activate buttons; Enter activates links
- [ ] Within composite widgets (tabs, menus, listboxes, trees), arrow keys move within and Tab moves out
- [ ] Modals trap focus and return focus to the trigger element on close
- [ ] Skip link (if present) works and is visible on focus

### Screen reader (WCAG 1.3.1, 2.4.2, 2.4.6, 4.1.2, 4.1.3)
- [ ] Page title describes the current page uniquely
- [ ] Heading structure (h1 → h2 → h3) creates a logical outline when navigating by headings
- [ ] All form inputs announce their label, required state, and any error
- [ ] Dynamic content changes (toasts, errors, loaded results) are announced via live regions
- [ ] Custom widgets (accordions, tabs, dropdowns) announce role and state (expanded/collapsed, selected)
- [ ] Route changes in SPAs are announced
- [ ] Images have alt text that makes sense in context (not redundant, not empty when informational)
- [ ] Icon buttons announce their purpose, not the icon name
- [ ] Decorative images are silent (`alt=""` or `aria-hidden="true"` as appropriate)

### Visual and motion (WCAG 1.4.1, 1.4.3, 1.4.10, 1.4.11, 1.4.12, 2.3.1, 2.3.3)
- [ ] Page usable at 200% zoom with no horizontal scroll at 1280px viewport
- [ ] Page reflows at 320px width without loss of content
- [ ] Text spacing can be overridden (line-height 1.5, paragraph spacing 2×, letter 0.12em, word 0.16em) without clipping
- [ ] No information conveyed by color alone (check with a grayscale filter)
- [ ] UI component borders/states meet 3:1 contrast against adjacent colors
- [ ] Animations respect `prefers-reduced-motion`
- [ ] No content flashes more than 3× per second
- [ ] Hover/focus tooltips are dismissable, hoverable, and persistent until dismissed

### Forms (WCAG 3.3.1–3.3.8)
- [ ] Errors identify the problem in text (not just color/icon)
- [ ] Error messages suggest correction when possible
- [ ] Required fields are indicated in the label (not just with a red asterisk)
- [ ] Input type matches content (email → `type="email"`, tel → `type="tel"`)
- [ ] Password fields allow paste (never block it)
- [ ] If CAPTCHA is used, there's a non-cognitive alternative (WCAG 2.2 — 3.3.8)
- [ ] Multi-step flows don't ask for re-entry of earlier data (WCAG 2.2 — 3.3.7)

### Cognitive and content (WCAG 3.1.3, 3.1.5, 3.2.*)
- [ ] Unusual words, jargon, and abbreviations are defined or expandable
- [ ] Error recovery is possible on destructive actions (confirm step or undo)
- [ ] Navigation is consistent across pages
- [ ] Interactive elements that look the same behave the same

---

## Not checked by either scanner

Tell the user explicitly that these WCAG criteria are **outside** what the scanners can evaluate, so they know the audit isn't complete on its own:

- 1.2.* — Time-based media (captions, audio descriptions, transcripts) — requires reviewing each media asset
- 1.4.2 — Audio control — can detect autoplay markup but not verify controls work
- 2.2.* — Timing — session timeouts, auto-updating content
- 2.3.1, 2.3.3 — Seizures and motion triggers — needs visual review of animations
- 3.1.3, 3.1.5 — Reading level, unusual words — language/content review
- 3.3.7, 3.3.8 — Redundant Entry and Accessible Authentication — flow review

Include this list in the "Not checked" section of the output report.
