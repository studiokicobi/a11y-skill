---
name: a11y-audit
description: Audit websites and web apps for WCAG 2.2 AA accessibility compliance. Use this skill whenever the user mentions accessibility, a11y, WCAG, screen readers, keyboard navigation, color contrast, ARIA, axe-core, alt text, focus indicators, or asks to check/test/audit a site for disability access, even if they don't explicitly say "accessibility." Also trigger when the user asks to review a frontend codebase for inclusivity, compliance, or Section 508 / EN 301 549 / ADA concerns. Produces a triaged report grouped by fix autonomy (auto-fixable, needs-human-input, manual-checklist) rather than raw severity dumps.
---

# a11y-audit

A WCAG 2.2 Level AA accessibility audit skill built for coding agents. The output format is the distinctive part: violations are grouped by **who can fix them**, not just by severity.

## Why this shape

Most a11y tools produce a flat list of violations sorted by severity. That's useful for a human reading a compliance report, but it's the wrong shape for an agent-plus-human workflow. An agent can confidently fix some issues (replacing `<div onClick>` with `<button>`, adding `type="button"`, remapping a known-bad Tailwind color class), needs the user's judgement for others (what *should* the alt text say, what label copy to use), and can't do a third category at all (did the focus order feel right, did NVDA announce the modal clearly).

This skill produces three groups in that order:

1. **Auto-fixable** — the agent can patch the code. Lists each issue with the exact edit. User approves, agent proceeds.
2. **Needs human input** — the agent drafts, the user decides. Lists each issue with a proposed fix and the decision needed.
3. **Manual checklist** — the user must do this themselves, with assistive tech. Lists capability-tagged assisted checks derived from the page and journey context.

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

### Step 2: Run the scan

Two scanners are available. Pick based on what's accessible:

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

**If the user gives a URL, run static plus runtime.** Add the stateful runner when the page depends on modals, route transitions, validation states, or other interaction-driven UI. Static tells you where to fix in the source; runtime confirms what the real DOM produces on page load; stateful confirms what appears after the user actually interacts. If the user only gives a directory, run static only and note in the report that runtime/stateful checks weren't performed.

**If the user gives a production URL but no source**, runtime only. Fixes will be framework-agnostic HTML/CSS suggestions.

### Step 3: Triage

Run the triage script to produce the three-group report:
```bash
python3 scripts/triage.py --static /tmp/a11y-static.json --runtime /tmp/a11y-runtime.json --stateful /tmp/a11y-stateful.json --output /tmp/a11y-report.md
```

The script applies the triage rules in `references/triage-rules.md`. Read that file before making triage decisions manually — do not classify issues from memory.

For repeated scans, compare against a saved baseline and carry status/waiver records:
```bash
python3 scripts/triage.py \
  --static /tmp/a11y-static.json \
  --runtime /tmp/a11y-runtime.json \
  --stateful /tmp/a11y-stateful.json \
  --status-file status.json \
  --baseline-file baseline.json \
  --output /tmp/a11y-report.md \
  --json-output /tmp/a11y-report.json
```

To save a fresh baseline after a confirmed run:
```bash
python3 scripts/baseline.py --report /tmp/a11y-report.json --output baseline.json
```

### Step 4: Present the report

Show the report to the user. Lead with a one-line summary:
> Found N issues: X auto-fixable, Y need your input, Z manual checks.

Then the three groups in order. For the auto-fixable group, end with:
> Reply "go" to apply auto-fixable fixes, or list which ones to skip.

Do not start editing files until the user responds.

### Step 5: Apply auto-fixes (on approval)

When the user approves:
1. For each auto-fixable issue, read the target file, apply the exact fix from the report, save.
2. After all fixes, re-run the static scan to confirm resolution and check for regressions.
3. Report the delta: what was resolved, what remains, any new issues introduced.

For the needs-human-input group, work through each item one at a time. Ask the user the specific decision, apply the fix, move to the next.

For the manual checklist, hand it off. Offer to come back and mark items as the user confirms them.

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

**Runtime scanner (axe-core via `a11y_runtime.js`):** runs the full axe-core rule set tagged `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22a`, `wcag22aa`, and `best-practice`. This includes computed color contrast, focus management, ARIA state after hydration, landmark regions, heading order, live regions, target size (WCAG 2.2 — 2.5.8), and many more. Axe-incomplete results (checks axe couldn't fully verify) are routed to Group 2 for manual confirmation.

**Stateful scanner (`a11y_stateful.js`):** runs Playwright journeys described in `references/journey_schema.md`, executes `click`, `press`, `fill`, `select`, `navigate`, and `assert` steps, and performs checkpoint axe scans after selected steps. Findings preserve `journey_step_id`, and the raw output records focus transitions, step failures, and checkpoint screenshots.

**Manual checklist (neither scanner can automate):** keyboard navigation (full tab walkthrough), screen reader testing, visual reflow, motion sensitivity, cognitive accessibility, and the WCAG 2.2 criteria that require flow review (2.5.7 Dragging, 3.3.7 Redundant Entry, 3.3.8 Accessible Authentication). See `references/triage-rules.md` for the full checklist.

**Not checked by either:** captions, audio descriptions, transcripts, timing-adjustable controls, seizure risk assessment, reading-level analysis, consistent-navigation review, error prevention on destructive actions. These WCAG criteria require media review or multi-page flow analysis, which is outside scope. The audit report lists these explicitly in the "Not checked" section so gaps are visible.

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

**Target**: <path or URL>
**Framework**: <detected>
**Standard**: WCAG 2.2 Level AA
**Date**: <ISO date>

## Summary
<one line: N issues total — X auto-fixable, Y need input, plus Z manual checks>

---

## Group 1: Auto-fixable (X issues)

The agent can apply these fixes without further input. Reply "go" to proceed, or list which to skip.

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

## Group 2: Needs your input (Y issues)

These need a decision from you. The agent can draft each fix once you answer.

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

## Group 3: Manual checklist

These require you to test with actual assistive technology or in the browser.

### 1. <assisted check title>
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

- **Not a replacement for manual testing with real assistive technology.** Automated tools catch around 30–40% of accessibility issues. The manual checklist exists because the rest require human judgement.
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
