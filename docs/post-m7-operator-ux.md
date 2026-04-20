# Post-M7 Operator UX Spec

## Status

Proposed

## Problem

The current product architecture is strong, but the operator workflow is still too fragmented.

Today a user can get good results, but they have to understand multiple internal scripts:

- `a11y_scan.py`
- `a11y_runtime.js`
- `a11y_stateful.js`
- `tokens.py`
- `triage.py`
- `baseline.py`
- `report.py`
- `cli.py`

That is acceptable for development, but it is not the right public product surface. The desired user experience is:

1. request an audit
2. receive a clear summary
3. know exactly what to do next
4. know where the generated artifacts live

## Product goal

The tool should feel like one product with two public workflows:

- `audit`
- `ci`

Everything else remains an internal implementation detail.

## Public command UX

The public command surface should be implemented in `scripts/cli.py` using subcommands.

### Public command 1: `audit`

Purpose:

- run the appropriate scanners
- generate the full artifact package
- print the human remediation handoff

Target syntax:

```bash
# Quick local audit of a codebase
python3 scripts/cli.py audit --path src/

# Quick local audit of a running site
python3 scripts/cli.py audit --url http://localhost:3000

# Full audit for a repo with source + runtime target
python3 scripts/cli.py audit \
  --path . \
  --url http://localhost:3000 \
  --mode full \
  --output-dir .artifacts/a11y/latest

# Full audit with explicit configs
python3 scripts/cli.py audit \
  --path . \
  --url http://localhost:3000 \
  --mode full \
  --runtime-config .a11y/runtime.config.json \
  --journey-config .a11y/journey.config.yaml \
  --token-file .a11y/tokens.json \
  --status-file .a11y/status.json \
  --baseline-file .a11y/baseline.json \
  --output-dir .artifacts/a11y/latest
```

Behavior:

- `--mode quick` runs the minimum useful workflow:
  - static when `--path` is present
  - runtime when `--url` is present
  - no stateful journeys unless explicitly configured
  - guided checks for the current target
- `--mode full` runs:
  - static
  - runtime
  - stateful when journey config is present
  - token analysis when token input is present
  - full guided checklist coverage for the current target
  - baseline comparison when baseline is present
- if only `--path` is present, run static-only and say that runtime/stateful were not run
- if only `--url` is present, run runtime-only and say source mapping will be limited
- the command always writes one artifact package and prints the canonical outcome line plus the full report path

### Public command 2: `ci`

Purpose:

- run the non-interactive regression workflow
- scope to changed files when requested
- emit the compact PR summary
- return deterministic exit codes

Target syntax:

```bash
python3 scripts/cli.py ci \
  --path . \
  --url http://localhost:3000 \
  --baseline-file .a11y/baseline.json \
  --changed-files .a11y/changed-files.txt \
  --output-dir .artifacts/a11y/ci \
  --ci
```

Behavior:

- no interactive prompts
- default threshold remains:
  - new findings only when baseline is present
  - severity `serious` or higher
  - confidence `high` or higher
  - manual findings non-blocking by default
- writes:
  - `report.json`
  - `summary.md`
  - any scanner artifacts needed for diagnosis
- prints one short outcome line plus the summary path

## Artifact package

Default package layout:

```text
.artifacts/a11y/<run-id>/
  manifest.json
  report.md
  report.json
  summary.md
  scanners/
    static.json
    runtime.json
    stateful.json
    tokens.json
  evidence/
    screenshots/
    dom/
    focus/
  inputs/
    runtime.config.json
    journey.config.json
    changed-files.txt
```

Rules:

- `manifest.json` is the index of the run
- report paths shown to the user should be relative to the repo root when possible
- if a scanner did not run, its file does not need to exist
- no default output should rely on `/tmp`
- the final console summary must point to:
  - `report.md`
  - `report.json`
  - `summary.md`
  - baseline file if written or updated

## Revised full report template

The full report should start with action, not metadata.

Target structure:

```md
# Accessibility Audit

Found 14 active findings: 5 safe to fix now, 4 need your decision, 5 to review manually. Also generated 7 guided checks for this target.

## Snapshot
- Target: ...
- Checked: static, runtime, stateful
- Baseline: 3 new, 8 unchanged, 3 waived
- Confidence: 7 high, 4 medium, 3 low
- Artifacts:
  - report.json
  - summary.md
  - scanners/runtime.json
  - evidence/screenshots/

## What to do next
- **Safe to fix now (5):** say "apply the safe fixes" and the agent will patch them.
- **Needs your decision (4):** say "walk me through the decisions" to answer them one at a time.
- **Test it yourself:** say "give me the checklist" — covers 5 scanner-flagged findings to verify and 7 guided checks. Or say "show me the manual findings" for just the scanner-flagged items.
- **Baseline:** say "save the baseline" to make this run the new reference, or "update the baseline" to refresh the existing one.

## Safe to fix now
...

## Needs your decision
...

## Test it yourself
...

## Not checked by this audit
...

## Waived (skipped on purpose)
...

## Resolved & tracked
...
```

Requirements:

- `Snapshot` is concise and scan-oriented
- `What to do next` is mandatory and must appear before `Safe to fix now`
- the report should name routes or journey steps when manual work is required
- if findings were excluded from changed-files scope due to low-confidence mapping, say so in `Snapshot`
- the report should never require the operator to infer the next action from the raw groups alone

## Revised PR summary template

Target structure:

```md
## Accessibility check

- Scope: changed files only (4 files)
- Active findings: 6
- Blocking findings: 2
- Buckets: 2 safe to fix, 1 need decisions, 3 to review manually
- Regression summary: new 2, unchanged 4
- Failing threshold: severity >= serious, confidence >= high, any-new=off, manual=off
- Excluded from scope: 3 findings with low-confidence mapping

### Blocking findings
- [serious/high][autofix][new] Missing alt text — resources/views/home.antlers.html:42
- [critical/high][needs_input][new] Color contrast — http://localhost:3000/contact

### Non-blocking findings
...
```

Requirements:

- include explicit blocker rationale, not just counts
- mention excluded low-confidence findings when changed-files mode is active
- stay short enough for PR consumption

## Specific files to change first

First wave:

- `.agents/skills/a11y-audit/scripts/cli.py`
  - add `audit` and `ci` subcommands
  - orchestrate scanners directly
  - own output-dir and artifact packaging
- `.agents/skills/a11y-audit/scripts/triage.py`
  - add `Snapshot` and mandatory `Next steps`
  - render artifact index
  - improve top-of-report operator handoff
- `.agents/skills/a11y-audit/scripts/report.py`
  - tighten PR summary wording
  - add excluded-low-confidence note
  - keep blocker explanations concise
- `.agents/skills/a11y-audit/fixtures/run_fixtures.py`
  - add audit/ci workflow fixtures
  - validate artifact layout and summary/report templates

Second wave:

- `.agents/skills/a11y-audit/README.md`
  - switch public docs to `audit` and `ci`
- `.agents/skills/a11y-audit/SKILL.md`
  - make agents use the new public workflow by default
- `AGENTS.md`
  - update repo validation examples if command invocation changes

Third wave, only where needed:

- `.agents/skills/a11y-audit/scripts/a11y_runtime.js`
- `.agents/skills/a11y-audit/scripts/a11y_stateful.js`
- `.agents/skills/a11y-audit/scripts/tokens.py`
- `.agents/skills/a11y-audit/scripts/baseline.py`

These should change only if the new orchestration or artifact packaging requires scanner-side adjustments.

## Acceptance criteria

- a first-time user can run one audit command without learning the internal scripts
- the tool writes one predictable artifact package
- the markdown report tells the user exactly what to do next
- PR summaries explain blockers and scoping clearly
- internal scripts remain available for debugging and fixture coverage
