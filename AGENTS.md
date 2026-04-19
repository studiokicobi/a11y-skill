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
- Run a static scanner smoke test: `python3 .agents/skills/a11y-audit/scripts/a11y_scan.py .agents/skills/a11y-audit/fixtures/html-basic --quiet --output /tmp/a11y-static.json`
- Run a token scanner smoke test: `python3 .agents/skills/a11y-audit/scripts/tokens.py .agents/skills/a11y-audit/fixtures/token-contrast/tokens.json --output /tmp/a11y-tokens.json`
- Build a baseline from a normalized JSON report: `python3 .agents/skills/a11y-audit/scripts/baseline.py --report /tmp/a11y-report.json --output /tmp/a11y-baseline.json`
- Compare a scan against a saved baseline: `python3 .agents/skills/a11y-audit/scripts/triage.py --static /tmp/a11y-static.json --tokens /tmp/a11y-tokens.json --json-output /tmp/a11y-report.json --baseline-file /tmp/a11y-baseline.json`
- Run a runtime script syntax check: `node --check .agents/skills/a11y-audit/scripts/a11y_runtime.js`
- Run a stateful script syntax check: `node --check .agents/skills/a11y-audit/scripts/a11y_stateful.js`
- Run the browser-backed fixture suite when browser launch is available: `python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py --live-runtime`
- There is no configured repo-level `pytest` or `ruff` workflow yet.

## Reporting expectations
- Reports must group findings into:
  1. auto-fixable
  2. needs input
  3. manual review
  4. not checked
- Each finding should include WCAG mapping, impact, confidence, and evidence source.

## Safe-fix rules
- Never invent alt text semantics.
- Never auto-apply fixes that require product or content intent.
- Never convert low-confidence runtime findings into direct source patches without explanation.
