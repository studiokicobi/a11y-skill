# PLAN.md

## Role of this file

This file is the execution plan for the repo.

- `docs/trd.md` defines what the product must become.
- `AGENTS.md` defines how work must be done in this repo.
- `PLAN.md` defines what to implement next, in what order, and what counts as done.

## Operating rules

- Work one milestone at a time.
- Do not start the next milestone unless explicitly instructed.
- Keep diffs scoped to the current milestone.
- Treat `.agents/skills/a11y-audit/` as the editable source tree.
- Treat `a11y-audit.skill` as a packaging artifact regenerated from the unpacked tree.
- Unless a path is explicitly repo-root-relative, skill file paths in this plan are relative to `.agents/skills/a11y-audit/`.
- Update tests and fixtures whenever behavior changes.
- Update docs and fixtures in the same change when schema or report contracts change.
- Record architecture-affecting decisions in `decisions/NNNN-short-slug.md`.
- Prefer conservative fixes over aggressive automation.

## Milestone order

- M0 — Baseline and repo alignment
- M1 — Core stabilization
- M2 — Schema and reporting hardening
- M3 — Runtime migration to Playwright
- M4 — Stateful journeys and manual review
- M5 — Baselines, fingerprints, and waivers
- M6 — Token and design-system analysis
- M7 — Source mapping and CI/PR integration
- M8 — Unified audit UX and report packaging

---

## M0 — Baseline and repo alignment

### Goal
Establish a clean starting point before feature work.

### Tasks
- Verify repo structure against `docs/trd.md`.
- Verify presence and consistency of `AGENTS.md`, `.agents/skills/a11y-audit/SKILL.md`, and `.agents/skills/a11y-audit/agents/openai.yaml`.
- Run current validation commands.
- Identify broken tests, missing dependencies, and outdated paths.
- Document any repo-structure mismatch that affects implementation.

### Deliverables
- a short baseline summary
- a list of broken or missing pieces
- working validation commands, or precise failure notes

### Done when
- the repo can be described accurately without guessing
- the current validation state is known

---

## M1 — Core stabilization

### Goal
Bring the existing auditor into alignment with the v2.1.1 core requirements.

### In scope
- current static/runtime/triage behavior
- fixtures and golden outputs
- no Playwright migration
- no stateful journeys

### Tasks
- Fix runtime-vs-static triage safety behavior.
- Preserve `origin_rule_id` for runtime findings where needed.
- Add wrapped-label support.
- Generate deterministic unique IDs for placeholder-label fixes.
- Tighten redundant-role handling conservatively.
- Improve rel-merge and diff generation behavior.
- Expand fixture coverage for known regressions.

### Required fixtures
- runtime `color-contrast` is not safe autofix
- wrapped label does not false-positive
- multiline JSX/HTML
- Angular `(click)` and Svelte `on:click`
- target-blank rel merge
- placeholder-label unique IDs

### Done when
- core fixtures pass
- no known mis-triaged safe fixes remain
- markdown and JSON output stay stable for current features

---

## M2 — Schema and reporting hardening

### Goal
Lock the normalized finding contract before larger feature expansion.

### In scope
- schema
- report structure
- coverage metadata
- statuses and waivers

### Tasks
- Implement the normalized finding schema from `docs/trd.md`.
- Add `origin_rule_id`, `scanner_version`, `detected_at`, `status`, `waiver`, and `confirmed_by`.
- Validate output against schema.
- Implement deterministic `not_checked` population from `references/wcag_coverage.md`.
- Ensure screenshot paths are relative to report output directory.
- Add status handling for `open`, `waived`, `fixed`, `resolved`, and `stale`.
- Add waiver expiration behavior.
- Add reason-for-group-assignment if missing.

### Required fixtures/tests
- schema validation
- waiver parsing
- expired waiver reopens finding
- stable `not_checked` output
- merged findings preserve `confirmed_by`

### Done when
- findings validate against schema
- report structure is deterministic
- waiver and status behavior is test-covered

---

## M3 — Runtime migration to Playwright

### Goal
Replace Puppeteer runtime scanning with Playwright.

### In scope
- runtime scanning only
- no full stateful flow support yet

### Tasks
- Replace Puppeteer with Playwright.
- Preserve current runtime feature parity:
  - axe integration
  - violation/incomplete handling
  - screenshot support
  - normalization
- Add per-page runtime configuration:
  - wait conditions
  - timeouts
  - route blocking
  - viewport
  - reduced motion
- Add minimal auth config support.
- Ensure secrets are never logged.

### Required fixtures/tests
- simple runtime scan passes
- auth failure is redacted and actionable
- screenshot paths are relative
- incomplete findings route correctly

### Done when
- Puppeteer is no longer required
- runtime tests pass on Playwright
- runtime output remains schema-compatible

---

## M4 — Stateful journeys and manual review

### Goal
Add interaction-state auditing and context-aware manual review generation.

### In scope
- first supported journey format
- first assisted checklist generator
- no auto-exploration

### Tasks
- Implement journey config parser.
- Implement step executor for:
  - `click`
  - `press`
  - `fill`
  - `select`
  - `navigate`
  - `assert`
- Run scan checkpoints after selected steps.
- Propagate `journey_step_id`.
- Record focus transitions and step failures.
- Generate manual-review items for:
  - keyboard navigation
  - focus visibility
  - headings
  - forms
  - dynamic announcements
  - reduced motion
  - use of color only
- Tag manual items by capability:
  - browser
  - keyboard
  - screen reader
  - visual

### Required fixtures/tests
- modal open/close
- form validation
- SPA route transition
- stateful findings retain step identity
- manual checklist reflects page/flow context

### Done when
- reports separate page-load and post-interaction findings
- representative journey fixtures pass

---

## M5 — Baselines, fingerprints, and waivers

### Goal
Enable repeatable comparison across runs and useful regression tracking.

### In scope
- baseline format
- fingerprinting
- comparison logic
- waiver lifecycle

### Tasks
- Implement baseline file format.
- Implement fingerprint rules:
  - static: `rule_id + source_file + stable_anchor`
  - runtime/stateful: `rule_id + normalized_selector + page_or_step_context`
- Implement stable-anchor precedence:
  1. `id`
  2. `data-testid`
  3. associated label
  4. `name`
  5. nearest heading
  6. line fallback with `unstable: true`
- Implement comparison categories:
  - new
  - unchanged
  - fixed
  - resolved
  - stale
  - waived

### Required fixtures/tests
- baseline comparison across runs
- stable anchor survives line shifts
- fallback marks `unstable: true`
- waiver expiration reopens finding
- stale baseline handling

### Done when
- repeated scans compare cleanly
- baseline behavior is stable enough for CI use

---

## M6 — Token and design-system analysis

### Goal
Add narrow, reliable design-system-level analysis.

### In scope
- contrast pairs
- focus indicator tokens
- color-only semantic tokens

### Tasks
- Parse the first supported token/theme sources.
- Add findings for:
  - color contrast pairs
  - focus indicator token issues
  - color-only semantic token issues
- Add blast-radius reporting:
  - one component
  - one file
  - design-system wide
- Generate nearby compliant suggestions where feasible.

### Required fixtures/tests
- token contrast failure
- missing/insufficient focus token
- color-only semantic token case

### Done when
- supported token inputs produce stable findings
- reports distinguish page-local and systemic issues

---

## M7 — Source mapping and CI/PR integration

### Goal
Add explainable source mapping and CI-ready output behavior.

### In scope
- narrow initial source mapping
- changed-files mode
- PR-friendly output
- deterministic CI behavior

### Tasks
- Implement source mapping using:
  - source maps where available
  - framework component stacks or debug attributes in development builds
- Add mapping confidence and explanation.
- Add changed-files mode.
- Add CI exit codes:
  - `0`
  - `1`
  - `2`
  - `3`
- Add GitHub/PR summary rendering.

### Required fixtures/tests
- mapping confidence tests
- CI exit-code tests
- changed-files scope tests
- PR summary rendering tests

### Done when
- CI mode is deterministic
- runtime findings can map back to likely source with explainable confidence

---

## M8 — Unified audit UX and report packaging

### Goal
Make the tool feel like one product with a clear operator workflow instead of a set of loosely related scripts.

This milestone is defined in more detail by `docs/post-m7-operator-ux.md`.

### In scope
- single public command surface for local audits and CI
- one artifact directory per run
- clearer markdown and PR-summary handoff
- no new scanner rules
- no new source-mapping techniques

### Tasks
- Define `cli.py audit` as the primary public audit entrypoint.
- Define `cli.py ci` as the primary CI/PR entrypoint.
- Keep lower-level scripts supported for fixtures and development, but move them out of the default user workflow.
- Standardize run artifacts under one output directory:
  - `report.md`
  - `report.json`
  - `summary.md`
  - `manifest.json`
  - copied input configs where present
  - scanner JSON and screenshots under predictable subdirectories
- Add a mandatory `Next steps` block near the top of the markdown report.
- Add an artifact index near the top of the markdown report.
- Make the PR summary explicitly state:
  - scope
  - blockers
  - groups
  - why a finding is blocking
  - when findings were excluded because mapping confidence was too low
- Document the new public workflow in `docs/trd.md`, `README.md`, and `SKILL.md`.

### Required fixtures/tests
- audit mode writes expected artifact layout
- audit mode quick-vs-full summary text
- markdown report includes `Next steps`
- PR summary includes threshold and blocker rationale
- changed-files summary notes excluded low-confidence findings

### Done when
- a first-time user can run one command and find the resulting artifacts without reading the internals
- the report tells the user exactly what action to take next
- public docs describe `audit` and `ci` as the supported workflow entrypoints

---

## Validation rules for every milestone

- Run relevant validation commands after changes.
- Update fixtures and golden outputs with behavior changes.
- Do not broaden a rule without at least one positive and one negative fixture.
- Keep schema changes intentional and version-aware.
- Keep WCAG coverage claims aligned with implementation.
- Keep autofix conservative.

## Validation commands

```bash
python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py
python3 .agents/skills/a11y-audit/scripts/a11y_scan.py .agents/skills/a11y-audit/fixtures/html-basic --quiet --output /tmp/a11y-static.json
node --check .agents/skills/a11y-audit/scripts/a11y_runtime.js
```
