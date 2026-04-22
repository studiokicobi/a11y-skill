---
name: a11y-audit
description: Audit websites and web apps for WCAG 2.2 AA accessibility compliance. Use this skill whenever the user mentions accessibility, a11y, WCAG, screen readers, keyboard navigation, color contrast, ARIA, axe-core, alt text, focus indicators, or asks to check/test/audit a site for disability access, even if they don't explicitly say "accessibility." Also trigger when the user asks to review a frontend codebase for inclusivity, compliance, or Section 508 / EN 301 549 / ADA concerns. Produces a triaged report grouped by fix autonomy into Safe to fix now, Needs your decision, and Test it yourself.
---

# a11y-audit

A WCAG 2.2 Level AA accessibility audit skill built for coding agents. The output format is the distinctive part: violations are grouped by **who can fix them**, not just by severity.

## Why this shape

Most a11y tools produce a flat list of violations sorted by severity. That's useful for a human reading a compliance report, but it's the wrong shape for an agent-plus-human workflow. An agent can confidently fix some issues (replacing `<div onClick>` with `<button>`, adding `type="button"`, remapping a known-bad Tailwind color class), needs the user's judgement for others (what *should* the alt text say, what label copy to use), and can't do a third category at all (did the focus order feel right, did NVDA announce the modal clearly).

This skill produces three buckets in that order:

1. **Safe to fix now** — the agent can patch these without further input once the user asks for that bucket.
2. **Needs your decision** — the agent drafts each fix once the user answers one question.
3. **Test it yourself** — these need a human in the browser or with assistive tech, including guided checks derived from the page and journey context.

## When to use this skill

Trigger on any request involving:
- Accessibility audit, WCAG, a11y, Section 508, ADA, EN 301 549
- "Is this accessible?" / "Can this be used with a screen reader?" / "Does this work with a keyboard?"
- Alt text, ARIA, focus indicators, color contrast, keyboard navigation, semantic HTML
- Inclusivity or disability access review of a codebase or site

## Workflow

### Step 1: Determine scope

Before running anything, establish:
- **Target**: a codebase directory? a running local URL? a deployed URL? All three?
- **Framework**: React/Next.js, Vue, Angular, Svelte, plain HTML, or mixed?
- **Scale**: a single component, a page, or a full site?

If the target isn't obvious from the request or working directory, ask the user briefly. Don't guess at a framework — detect it (check `package.json`, file extensions) or ask.

### Step 2: Run the public workflow

Default to the public orchestrator, not the internal scripts:

```bash
# Quick audit
python3 scripts/cli.py audit --path <path>
python3 scripts/cli.py audit --url <url>

# Full audit with explicit configs
python3 scripts/cli.py audit \
  --path <path> \
  --url <url> \
  --mode full \
  --runtime-config runtime.config.json \
  --journey-config journey.config.json \
  --token-file tokens.json \
  --baseline-file baseline.json \
  --status-file status.json \
  --output-dir .artifacts/a11y/latest
```

Use `audit` for operator-facing local runs. It writes one artifact package containing:

- `report.md`
- `report.json`
- `summary.md`
- `manifest.json`
- scanner JSON under `scanners/`
- evidence under `evidence/`

The top of `report.md` must tell the user what to do next before it lists the buckets.

### Step 3: Choose the scanners

The orchestrator decides which scanner inputs to run from the supplied path, URL, and optional configs. The underlying scanners are still:

**Static scan** (default, always available):
```bash
python3 scripts/a11y_scan.py <path> --output /tmp/a11y-static.json
```
Fast, catches source-visible issues: missing `alt`, `<div onClick>`, hardcoded low-contrast colors, missing labels, missing `lang`, `outline: none` without replacement, etc. Use this for every audit. No dependencies beyond Python stdlib.

**Runtime scan** (when a URL is available):
```bash
node scripts/a11y_runtime.js --url <url> --output /tmp/a11y-runtime.json
```
Uses Playwright + axe-core to analyze the rendered DOM. Catches computed contrast, focus management, rendered ARIA states, semantic structure after hydration, and axe-incomplete findings that need manual verification. Auto-installs `playwright` and `axe-core` on first run.

For authenticated or configured scans, use:
```bash
node scripts/a11y_runtime.js --config runtime.config.json --output /tmp/a11y-runtime.json
```
The runtime config supports storage-state auth, headers/cookies auth, per-page wait conditions, route blocking, viewport, reduced motion, and optional screenshots.

**Stateful journey scan** (when the page requires interactions):
```bash
node scripts/a11y_stateful.js --config journey.config.json --output /tmp/a11y-stateful.json
```
Uses Playwright + axe-core checkpoint scans after scripted actions. Emits stateful findings with `journey_step_id`, plus focus transitions, step failures, and checkpoint screenshots. The supported config shape lives in `references/journey_schema.md`.

**Token scan** (when a repo has explicit design-token JSON):
```bash
python3 scripts/tokens.py design-tokens.json --output /tmp/a11y-tokens.json
```
This is intentionally narrow. It currently supports one explicit JSON token schema for contrast pairs, focus indicator tokens, and color-only semantic tokens. Use it when the repo has a maintained token file and you want design-system-level findings with blast-radius reporting.

**If the user gives a URL, run static plus runtime.** Add the stateful runner when the page depends on modals, route transitions, validation states, or other interaction-driven UI. Static tells you where to fix in the source; runtime confirms what the real DOM produces on page load; stateful confirms what appears after the user actually interacts. If the user only gives a directory, run static only and note in the report that runtime/stateful checks weren't performed.

**If the repo also includes a supported token file, run the token scanner too.** Token findings are design-system issues, not page-local DOM issues, and should be reported alongside the other findings rather than merged into static source rules.

**If the user gives a production URL but no source**, runtime only. Fixes will be framework-agnostic HTML/CSS suggestions.

### Step 4: CI mode

For CI or PR workflows, use the public `ci` command:
```bash
python3 scripts/cli.py ci \
  --path . \
  --url http://localhost:3000 \
  --baseline-file baseline.json \
  --changed-files changed-files.txt \
  --output-dir .artifacts/a11y/ci \
  --ci
```
By default, CI blocks on new `serious` or `critical` findings with `high` confidence. Manual-review findings stay non-blocking unless explicitly opted in.

Keep `triage.py`, `report.py`, and `baseline.py` for fixtures, debugging, and advanced usage. The script still applies the triage rules in `references/triage-rules.md`, and you should read that file before making triage decisions manually.

## Conversation contract

After `audit` completes, reuse the exact generated `outcome_body` string from that run. Do not recompute it, summarize it, or paraphrase it. The CLI prints it to stdout as the first line; it is also persisted in `manifest.json` at `outcome.body` so you can reload it from a prior run without rescanning. Wrap it exactly like this:

`Audit complete. {outcome_body} Full report: \`{path}\`. What would you like to do?`

Recognized user intents:
- `apply the safe fixes` or `fix what you can`: work through **Safe to fix now**, edit files, rerun the static scan, and report only the delta.
- `walk me through the decisions` or `start the decisions`: work through **Needs your decision** one item at a time. Ask one question, wait, then draft and apply the fix after confirmation.
- `give me the checklist` or `what do I test?`: render **Test it yourself** as the actionable list for this run, covering both `Manual findings` and `Guided checklist`.
- `show me the manual findings`: render only the `Manual findings` subsection from **Test it yourself**.
- `save the baseline` or `update the baseline`: promote the previously generated report for the selected run. Never re-scan implicitly. Use the most recently announced `manifest.json` or `report.json` from this conversation unless the user names a different run. If none has been announced, or the requested run is ambiguous, ask. After confirmation, use `python3 scripts/cli.py promote-baseline --report <path/to/report.json> --baseline-file <path>`.
- `run the CI check` or `check for regressions`: run `python3 scripts/cli.py ci ...` against the chosen baseline and report blockers with the generated summary path.
- `re-audit`: rerun `python3 scripts/cli.py audit ...` with the same inputs and report the delta from the last run.

Intent synonyms:
- `go ahead`, `do it`, and `yes` only count when the agent has just proposed one specific action. They are not standalone commands.
- Never ask the user to reply with `go`.

Pause points:
1. After the audit, before any file edits.
2. Between each **Needs your decision** item. Never batch multiple decisions.
3. Before saving or updating a baseline. Confirm that this run becomes the new reference.

Hand-off etiquette for **Test it yourself**:
- Offer to track checklist progress in chat as the user works through it.
- Do not claim the audit is complete while checklist items remain unchecked unless the user explicitly closes them out.
- If the user asks for just the scanner-routed items, show `Manual findings` only. If they ask what to test, show both `Manual findings` and `Guided checklist`.

What the agent must not do:
- Do not edit files unless the user has expressed one of the apply intents above.
- Do not auto-run `ci` after `audit`.
- Do not restate the full report after every action; show only what changed.
- Do not use numbered group labels in chat. Use **Safe to fix now**, **Needs your decision**, and **Test it yourself**.

## Fix patterns

Framework-specific before/after code for every violation type lives in `references/`:
- `references/fix-patterns-react.md` — React, Next.js, JSX
- `references/fix-patterns-vue.md` — Vue, Nuxt, SFCs
- `references/fix-patterns-angular.md` — Angular templates and components
- `references/fix-patterns-svelte.md` — Svelte, SvelteKit
- `references/fix-patterns-html.md` — Plain HTML and vanilla JS

Load only the file(s) matching the detected framework. Do not load all of them.

## What the scanners check

The skill honestly splits coverage into three tiers. Don't claim more than this.

**Static scanner rules (implemented in `a11y_scan.py`):**
- 1.1.1 — `<img>` missing alt
- 1.3.1 — `<input>` without label; placeholder used as only label
- 1.4.2 — `<video>` / `<audio>` with autoplay
- 1.4.3 — Low-contrast CSS hex colors; low-contrast Tailwind text classes
- 2.1.1 — Non-interactive element (div, span, etc.) with onClick handler
- 2.4.3 — Positive `tabindex` values (disrupts natural tab order)
- 2.4.7 — `outline: none` without a `:focus-visible` replacement nearby
- 3.1.1 — `<html>` missing `lang` attribute
- 4.1.2 — Redundant ARIA roles on semantic elements; `aria-hidden="true"` on focusable elements
- best-practice — `target="_blank"` without `rel="noopener noreferrer"`

**Runtime scanner (axe-core via `a11y_runtime.js`):** runs the full axe-core rule set tagged `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22a`, `wcag22aa`, and `best-practice`. This includes computed color contrast, focus management, ARIA state after hydration, landmark regions, heading order, live regions, target size (WCAG 2.2 — 2.5.8), and many more. Axe-incomplete results (checks axe couldn't fully verify) are routed to **Needs your decision** for manual confirmation.

When runtime/stateful DOM snippets expose debug source hints such as `data-source-file`, `data-source-line`, `data-source-loc`, or `data-component-stack`, the normalized report maps those findings back to likely source files with `high` or `medium` confidence. Without those hints, runtime/stateful mapping remains `low` confidence and should stay informational.

**Stateful scanner (`a11y_stateful.js`):** runs Playwright journeys described in `references/journey_schema.md`, executes `click`, `press`, `fill`, `select`, `navigate`, and `assert` steps, and performs checkpoint axe scans after selected steps. Findings preserve `journey_step_id`, and the raw output records focus transitions, step failures, and checkpoint screenshots.

**Guided checklist (neither scanner can automate):** keyboard navigation (full tab walkthrough), screen reader testing, visual reflow, motion sensitivity (2.3.3), dragging gestures (2.5.7), and use-of-color-only verification. Flow-specific WCAG 2.2 criteria (3.3.7 Redundant Entry, 3.3.8 Accessible Authentication) are **not** covered by the checklist — they require hand-rolled tests against your specific flow and are listed under "Not checked" so the gap stays visible. See `references/triage-rules.md` for the full checklist.

**Not checked by either:** captions and audio descriptions (1.2.\*), timing-adjustable controls (2.2.\*), seizure risk (2.3.1), multi-point gestures / pointer cancellation / motion actuation (2.5.1, 2.5.2, 2.5.4), cross-page consistency (3.2.3, 3.2.4, 3.2.6), error suggestion and destructive-action prevention (3.3.3, 3.3.4), Redundant Entry (3.3.7), and Accessible Authentication (3.3.8). These criteria require media review, multi-page flow analysis, or a visual pass the scanner cannot perform. `references/wcag_coverage.md` is the full authoritative matrix; the audit report surfaces every `out-of-scope` row under **Not checked** so the gap stays visible.

## Color contrast

`scripts/contrast_checker.py` validates color pairs and suggests accessible alternatives:
```bash
# Single pair
python3 scripts/contrast_checker.py --fg "#999" --bg "#fff"

# Scan a CSS file
python3 scripts/contrast_checker.py --file src/styles.css

# Scan Tailwind classes in a directory
python3 scripts/contrast_checker.py --tailwind src/
```

A curated map of common inaccessible colors to accessible alternatives lives in `references/contrast-alternatives.md`. Use it when proposing contrast fixes — don't invent replacement colors.

## Output contract

The triaged report is markdown with this structure. Do not deviate.

```
# Accessibility Audit Report

**Date**: <ISO date>

<one line: exact generated outcome_body wording, with markdown emphasis only>

## Snapshot
- Target: <path or URL>
- Framework: <detected>
- Standard: WCAG 2.2 Level AA
- Checked: <static, runtime, stateful, token>
- Baseline: <none | summary>
- Confidence: <high N, medium N, low N>
Artifacts:
- `report.json`
- `summary.md`
- `manifest.json`
- `scanners/<scanner>.json`

## What to do next
- **Safe to fix now (X):** say "apply the safe fixes" and the agent will patch them.
- **Needs your decision (Y):** say "walk me through the decisions" to answer them one at a time.
- **Test it yourself:** <canonical variant based on manual findings count and guided checklist count>
- **Baseline:** <canonical save/update baseline wording>

---

## Safe to fix now (X)

_The agent can apply these without further input. Say "apply the safe fixes" to proceed, or list which to skip._

### 1. [WCAG criterion] — <short title>
**Location**: `path/to/file.tsx:42`
**Issue**: <what's wrong, one sentence>
**Fix**:
```diff
- <old code>
+ <new code>
```

<... more items ...>

---

## Needs your decision (Y)

_Each item asks one question. Say "walk me through the decisions" and the agent will go one at a time._

### 1. [WCAG criterion] — <short title>
**Location**: `path/to/file.tsx:42`
**Issue**: <what's wrong>
**Decision needed**: <specific question>
**Current code**:
```
<relevant code>
```

<... more items ...>

---

## Test it yourself

_These require a human in the browser or with assistive tech — the things automated scanners can't reliably check._

### Manual findings (M)

#### 1. [WCAG criterion] — <short title>
**Location**: `path/to/file.tsx:42`
**Issue**: <what's wrong>

### Guided checklist (C)

#### 1. <assisted check title>
**Capability**: `keyboard|screen reader|visual|browser`
**WCAG**: <criteria>
**Context**: <page or step context>
**How to test**:
- [ ] <step>
**Expected result**:
- [ ] <outcome>

---

## Not checked by this audit
<list of WCAG criteria the scanners can't evaluate, so the user knows the gaps>
```

## What this skill does NOT do

- **Not a replacement for manual testing with real assistive technology.** Automated checks cover only part of accessibility work. The **Test it yourself** bucket exists because the rest requires human judgement.
- **Not legal advice.** WCAG compliance and legal requirements (ADA, Section 508, EN 301 549, EAA) are related but distinct. The skill flags violations; it doesn't certify compliance.
- **Not a design tool.** If contrast is failing because the brand palette is fundamentally inaccessible, the skill surfaces that but won't redesign the palette.

## Common pitfalls

When applying fixes, avoid these mistakes. Full list in `references/pitfalls.md`:
- Adding `role="button"` to a `<div>` instead of using `<button>`
- Setting `tabindex="0"` on non-interactive elements
- Using `aria-label` on generic containers where it's likely ignored
- Using `display: none` when `.sr-only` is what's needed
- Empty `alt=""` on informational images (that marks them decorative)
- Removing `outline` without providing a `:focus-visible` replacement
