# AGENTS.md

## Repository purpose
This repo develops an accessibility audit skill for Codex/Claude-style agent workflows.

The editable source of truth is `.agents/skills/a11y-audit/`.
Treat `a11y-audit.skill` as a distributable artifact, not the file to edit directly.

## Working rules
- Fix-autonomy is the primary triage axis.
- Severity/impact is secondary metadata for urgency and scheduling.
- Do not classify runtime color-contrast findings as safe autofix without source-aware confidence.
- Prefer conservative fixes over aggressive autofix.
- Keep WCAG coverage claims honest and explicit.

## Implementation rules
- Unless noted otherwise, skill-relative paths in this repo refer to `.agents/skills/a11y-audit/`.
- Update fixtures and tests whenever scanner behavior changes.
- Add or update golden expected outputs for report-format changes.
- Do not broaden rules without adding at least one positive and one negative fixture.
- Preserve stable JSON schema for findings unless intentionally versioning it.
- Stay within the current milestone in PLAN.md unless explicitly instructed otherwise.
- Record architecture-affecting decisions in decisions/NNNN-short-slug.md.
- If schema or report contracts change, update docs and fixtures in the same change.

## Commands
- Run fixture runner from repo root: `python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py`
- Run a public audit smoke test: `python3 .agents/skills/a11y-audit/scripts/cli.py audit --path .agents/skills/a11y-audit/fixtures/html-basic --output-dir /tmp/a11y-audit-smoke --detected-at 2026-01-02T03:04:05Z`
- Run a public CI smoke test: `python3 .agents/skills/a11y-audit/scripts/cli.py ci --runtime .agents/skills/a11y-audit/fixtures/ci-changed-files-blocking/runtime.json --changed-files .agents/skills/a11y-audit/fixtures/ci-changed-files-blocking/changed-files.txt --output-dir /tmp/a11y-ci-smoke --detected-at 2026-01-02T03:04:05Z --ci`
- Run a static scanner smoke test: `python3 .agents/skills/a11y-audit/scripts/a11y_scan.py .agents/skills/a11y-audit/fixtures/html-basic --quiet --output /tmp/a11y-static.json`
- Run a token scanner smoke test: `python3 .agents/skills/a11y-audit/scripts/tokens.py .agents/skills/a11y-audit/fixtures/token-contrast/tokens.json --output /tmp/a11y-tokens.json`
- Build a baseline from a normalized JSON report: `python3 .agents/skills/a11y-audit/scripts/baseline.py --report /tmp/a11y-report.json --output /tmp/a11y-baseline.json`
- Compare a scan against a saved baseline: `python3 .agents/skills/a11y-audit/scripts/triage.py --static /tmp/a11y-static.json --tokens /tmp/a11y-tokens.json --json-output /tmp/a11y-report.json --baseline-file /tmp/a11y-baseline.json`
- Render a CI/PR summary and exit with CI codes from raw scanner JSON: `python3 .agents/skills/a11y-audit/scripts/cli.py ci --runtime /tmp/a11y-runtime.json --baseline-file /tmp/a11y-baseline.json --output-dir /tmp/a11y-ci --ci` (the summary is written to `/tmp/a11y-ci/summary.md`)
- Render a PR summary from an existing normalized report: `python3 .agents/skills/a11y-audit/scripts/report.py --report /tmp/a11y-report.json --summary-output /tmp/a11y-pr-summary.md --ci`
- Run a runtime script syntax check: `node --check .agents/skills/a11y-audit/scripts/a11y_runtime.js`
- Run a stateful script syntax check: `node --check .agents/skills/a11y-audit/scripts/a11y_stateful.js`
- Run the browser-backed fixture suite when browser launch is available: `python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py --live-runtime`
- There is no configured repo-level `pytest` or `ruff` workflow yet.

## Skill surface hierarchy
The skill exposes a tiered command surface. Preserve this hierarchy when making changes — promoting an internal script to the user-facing path, or hiding a public command, requires updating `SKILL.md`, this file, and the fixture suite in the same change.

1. **Public orchestrator** (`scripts/cli.py`) — what end users and invoking agents run directly:
   - `cli.py audit` — single-shot local audit, writes a full artifact package (`report.md`, `report.json`, `summary.md`, `manifest.json`, scanner JSON, evidence).
   - `cli.py ci` — PR/CI mode, writes `summary.md` and exits with CI gating codes based on the baseline.
   - `cli.py promote-baseline` — promote a prior `report.json` to the saved baseline.
2. **Internal scripts** — invoked by the orchestrator, retained for fixtures, debugging, and advanced one-offs:
   - `scripts/a11y_scan.py` — static source scanner
   - `scripts/a11y_runtime.js` — Playwright + axe-core runtime scan
   - `scripts/a11y_stateful.js` — Playwright journey scan (checkpoint axe scans after scripted actions)
   - `scripts/tokens.py` — design-token scanner
   - `scripts/triage.py` — normalize + triage scanner output into a report
   - `scripts/report.py` — render markdown/summary from a report JSON
   - `scripts/baseline.py` — build or promote a baseline file
   - `scripts/contrast_checker.py` — color pair / CSS / Tailwind contrast utility

End users and invoking agents should see the public orchestrator first. Drop to internal scripts only for fixtures, reproduction, or debugging. Internal scripts remain stable so fixtures can target them directly — do not rewrite their CLIs casually.

## Reporting expectations
- Use named buckets (Safe to fix now / Needs your decision / Test it yourself) in user-facing text. Numbered group labels are not used.
- Reports must group findings into:
  1. auto-fixable
  2. needs input
  3. manual review
  4. not checked
- Each finding should include WCAG mapping, impact, confidence, and evidence source.
- The `Not checked` section is populated from rows flagged `out-of-scope` in `references/wcag_coverage.md`. Keep that matrix, `references/triage-rules.md`, and `scripts/triage.py → RULE_TO_GROUP` in sync when rules are added, reclassified, or removed.

## Conversation contract
**`SKILL.md` is the single source of truth for the user-facing conversation contract.** The list below is a summary for dev context only — it is *not* authoritative. Before changing intent handling, pause-point behavior, or any other conversational rule, read the corresponding section of `SKILL.md` and change that file first. Any drift found during review should be fixed in `SKILL.md` and propagated here, never the other way around.

A dev change must not regress any of the invariants below — if one needs to change, update `SKILL.md`, this file, and the relevant fixtures in the same change.

After an audit completes, the skill reuses the exact `outcome_body` string produced by the run (printed to stdout and persisted at `manifest.json → outcome.body`). Do not recompute, summarize, or paraphrase it. Render the report path as a Markdown file link using an absolute filesystem path. If the CLI prints a relative report path, resolve it against the audited repo before rendering the link. Wrap the link target in angle brackets when the path contains spaces or other Markdown-sensitive characters. The canonical wrapper is:

`Audit complete. {outcome_body} Full report: [report.md]({absolute_path}). What would you like to do?`

For paths with spaces or parentheses, use:

`Audit complete. {outcome_body} Full report: [report.md](<{absolute_path}>). What would you like to do?`

Recognized user-intent summary (authoritative text lives in `SKILL.md`):
- `apply the safe fixes` / `fix what you can` → patch **Safe to fix now**, rerun the static scan, report the delta only.
- `walk me through the decisions` / `start the decisions` → work **Needs your decision** one item at a time; ask, wait, then apply after confirmation.
- `give me the checklist` / `what do I test?` → render **Test it yourself** (`Manual findings` + `Guided checklist`).
- `show me the manual findings` → render only the `Manual findings` subsection.
- `save the baseline` / `update the baseline` → promote the previously generated report via `cli.py promote-baseline --report <path> --baseline-file <path>`. Default to the most recently announced `manifest.json` / `report.json` from this conversation; if none has been announced or the target run is ambiguous, ask before acting. Confirm with the user before writing — this run becomes the new reference point. Never re-scan implicitly.
- `run the CI check` / `check for regressions` → run `cli.py ci ...` against the chosen baseline and report blockers.
- `re-audit` → rerun the same `cli.py audit ...` invocation and report the delta.

Pause points the skill must enforce (and tests must preserve):
1. After the audit, before any file edits.
2. Between each **Needs your decision** item — never batch multiple decisions.
3. Before saving or updating a baseline — confirm this run becomes the new reference.

Hand-off etiquette for **Test it yourself** (reflecting `SKILL.md`):
- Offer to track checklist progress in chat while the user works through it.
- Do not claim the audit is complete while checklist items remain unchecked unless the user explicitly closes them out.
- If the user asks for the scanner-routed items only, show `Manual findings` only. If they ask what to test, show both `Manual findings` and `Guided checklist`.

Invariants a dev change must not regress:
- Do not edit files unless the user has expressed an apply intent.
- Do not auto-run `ci` after `audit`.
- Do not restate the full report after every action — show only the delta.
- Do not use numbered group labels in user-facing text. Only **Safe to fix now**, **Needs your decision**, and **Test it yourself**.
- `go ahead` / `do it` / `yes` only count when the agent has just proposed one specific action. They are never standalone commands.
- Never ask the user to reply with `go`.

## Safe-fix rules
- Never invent alt text semantics.
- Never auto-apply fixes that require product or content intent.
- Never convert low-confidence runtime findings into direct source patches without explanation.
