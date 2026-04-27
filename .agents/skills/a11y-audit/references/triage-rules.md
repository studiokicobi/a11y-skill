# Triage Rules

Every detected violation gets classified into one of three groups. The rule is **what does the agent need from the user to fix it?**

- **Safe to fix now (auto)**: agent has everything it needs. One command applies the fix.
- **Needs your decision (input)**: agent knows *where* and *how*, but needs a content/copy/design decision.
- **Test it yourself (manual)**: automated tools can't verify this. User must test it.

When classifying a new violation that isn't in the tables below, apply the rule above and use judgement. When in doubt, prefer "Needs your decision" over "Safe to fix now" — a wrong auto-fix is worse than a pending one. Unknown axe rules default to `input` (see `scripts/a11y_runtime_common.js` → `AXE_TRIAGE_HINT`).

The source of truth for the actual mapping is `scripts/triage.py` → `RULE_TO_GROUP`. This doc is a human-readable mirror.

---

## Safe to fix now (auto)

These fixes have a deterministic correct output given what the scanner already knows, and a matching template in `scripts/triage.py` → `render_fix`.

| Rule ID | WCAG | What the scanner detects | Auto-applied fix |
| --- | --- | --- | --- |
| `redundant-role` | 4.1.2 | ARIA role that duplicates the element's implicit role (`<nav role="navigation">`, `<main role="main">`, `<button role="button">`, `<article role="article">`) | Remove the redundant `role` attribute |
| `target-blank-no-noopener` | best practice | `<a target="_blank">` without `rel="noopener"` / `rel="noreferrer"` | Merge `noopener noreferrer` into the existing `rel` (or add `rel="noopener noreferrer"` if absent) |
| `input-placeholder-as-label` | 1.3.1, 3.3.2 | `<input placeholder="...">` with no associated `<label>` | Add a `<label for="...">` using the placeholder text, and give the input a matching `id` (framework-aware: `htmlFor` vs `for`) |
| `tailwind-low-contrast` | 1.4.3 | Tailwind utility class listed in `references/contrast-alternatives.md` that fails AA on the likely background | Swap to the mapped accessible Tailwind class |
| `css-low-contrast` | 1.4.3 | Hex/rgb/named color in CSS that's listed in `references/contrast-alternatives.md` | Swap to the mapped accessible color |
| `outline-none` | 2.4.7, 2.4.11 | `outline: none` / `outline: 0` in CSS on an interactive selector with no `:focus-visible` replacement | Append a `:focus-visible` block with a visible outline |
| `aria-hidden-focusable` | 4.1.2 | `aria-hidden="true"` on a focusable element itself (`<a>`/`<button>`/`<input>`/`<select>`/`<textarea>`) | Remove the `aria-hidden` attribute |

---

## Needs your decision (input)

The agent can locate the issue and describe the fix shape, but the *content* needs a human.

| Rule ID | WCAG | What the scanner detects | Decision prompt |
| --- | --- | --- | --- |
| `clickable-div` | 2.1.1, 4.1.2 | `<div>`/`<span>`/heading/etc with an onClick handler (React `onClick`, Vue/HTML `onclick`, Svelte `on:click`, Angular `(click)`) and no interactive role + tabindex pair | "Is this control an action (`<button type=\"button\">`) or navigation (`<a href>`)? The scanner only sees the opening tag, so the closing tag rewrite + element choice need a human." |
| `img-missing-alt` | 1.1.1 | `<img>` with no `alt` attribute | "What does this image convey? (For decorative images, we'll use `alt=""`.)" |
| `input-missing-label` | 1.3.1 | `<input>`/`<select>`/`<textarea>` with no associated `<label>` and no `aria-label` / `aria-labelledby` | "What should this input be labeled?" |
| `positive-tabindex` | 2.4.3 | `tabindex` value greater than 0 | "Is this tab order deliberate? If not, we'll remove the positive tabindex." |
| `media-autoplay` | 1.4.2 | `<audio>` / `<video>` with an `autoplay` attribute | "Keep autoplay with pause controls, or remove autoplay entirely?" |
| `heading-order` | 1.3.1 | Heading level skipped (e.g. `<h1>` → `<h3>`) | "Should the out-of-order heading be downgraded/upgraded to match the sequence, or should we restructure the page hierarchy?" |
| `icon-only-control` | 4.1.2 | Button/link whose only content is an icon and that has no `aria-label` / `aria-labelledby` / visible text | "What does this control do? We'll add an `aria-label` so screen readers announce its purpose." |
| `duplicate-id` | 4.1.1 | Same `id` on two or more elements in the same document | "Which element keeps the id, and what should the other one be renamed to? (Search the codebase first — CSS selectors, JS lookups, aria-labelledby/aria-describedby, label[for], and anchor #hashes may depend on it.)" |
| `html-missing-lang` | 3.1.1 | `<html>` without a `lang` attribute | "What BCP-47 language tag should go on `<html lang>`? (e.g. `en`, `en-GB`, `sv`, `fr-CA`. Screen readers use this to pick pronunciation, so it must match the document's primary language — don't just default to `en`.)" |
| `aria-hidden-focusable` (container) | 4.1.2 | `aria-hidden="true"` on a container element that has a focusable descendant (same `rule_id` as the auto case; distinguished by `fix_data.pattern == "aria_hidden_container"`). Conservative same-file detection — skipped when any nested `aria-hidden="false"` override or `tabindex="-1"` on every focusable descendant suppresses the hazard. | "A container with aria-hidden=\"true\" has a focusable descendant, so keyboard users can land on something screen readers ignore. Pick one: remove aria-hidden from the container, add tabindex=\"-1\" to the descendant, or move the descendant out of the hidden subtree." |
| `token-low-contrast` | 1.4.3 | Design-token pair whose computed contrast fails AA | "Which nearby compliant token value should replace this failing pair?" |
| `token-focus-indicator` | 2.4.7, 2.4.11 | Focus-indicator token missing or below the 3:1 / 2-px threshold | "Should we strengthen the focus ring color, width, or both for this token set?" |
| `token-color-only-semantic` | 1.4.1 | Semantic token (success/error/warning/info) that relies on color alone — no paired icon, label, or shape | "What non-color cue should accompany this semantic token across the design system?" |

Runtime (axe-core) rules that aren't individually mapped fall back to the scanner's `triage_hint` value, which defaults to `input` for any rule the scanner hasn't explicitly vetted. See `scripts/a11y_runtime_common.js` → `AXE_TRIAGE_HINT` for the current opt-in set (shared between `a11y_runtime.js` and `a11y_stateful.js`).

---

## Test it yourself (manual)

The triage report always includes a **Guided checklist** of manual checks, scoped to what was audited:

- **Page or flow audits** (static / runtime / stateful present): keyboard tab order, focus visibility & return, heading outline & page title, zoom/reflow/text-spacing, reduced motion, dragging gestures, use-of-color-only. Additional items are added when the audit touched forms, overlays, or route changes — see `_collect_manual_context` in `scripts/triage.py`.
- **Token-only audits** (only `--tokens` present): use-of-color-only across semantic tokens, theme coverage, rendered composition at component boundaries. Page-flow checks are suppressed because there is no rendered page to exercise.

See `scripts/triage.py` → `generate_manual_review_items` for the authoritative set.

---

## Not checked by either scanner

The report renders a `Not checked` section listing WCAG criteria that neither scanner can evaluate, so the user knows the audit isn't complete on its own. The current set is authoritative in `scripts/triage.py` → `NOT_CHECKED_CRITERIA` (or equivalent constant). High-level coverage:

- **1.2.\*** — Time-based media (captions, audio descriptions, transcripts) — requires reviewing each media asset.
- **2.2.\*** — Timing — session timeouts, auto-updating content.
- **2.3.1** — Three flashes / seizure risk — needs a visual frame-rate pass. (2.3.3 motion-from-interactions **is** in the checklist.)
- **2.5.1, 2.5.2, 2.5.4** — Multi-point gestures, pointer cancellation, motion actuation — not automated and not in the checklist. (2.5.7 dragging **is** in the checklist; 2.5.3 Label in Name and 2.5.8 Target Size run under axe at runtime.)
- **3.2.3, 3.2.4, 3.2.6** — Cross-page consistency — out of scope for a single-page/flow audit.
- **3.3.3, 3.3.4** — Error suggestion and destructive-action prevention — flow-specific manual review.
- **3.3.7, 3.3.8** — Redundant Entry and Accessible Authentication — flow review.

See `references/wcag_coverage.md` for the full per-criterion matrix of what is / isn't covered today.
