# a11y-audit

WCAG 2.2 Level AA accessibility audit skill for Claude Code, Codex, and other agent runtimes.

Produces a **triaged report grouped by fix autonomy** — **Safe to fix now**, **Needs your decision**, and **Test it yourself** — rather than a flat severity-sorted list. This matches how a human-plus-agent workflow actually proceeds: the agent patches what it can on approval, drafts what needs a decision, and hands off what requires assistive-tech testing.

## What it checks

- **Static analysis** of source files for issues the agent can often fix directly or map cleanly back to source.
- **Runtime analysis** via Playwright + axe-core for rendered DOM behavior such as computed contrast, focus management, and hydrated semantics.
- **Stateful journey analysis** for interaction-driven states, with findings tagged by journey step.
- **Guided human checks** for the accessibility work automated scanners cannot verify reliably.

## Install

### Claude Code

Place the `a11y-audit/` directory in your skills folder:

```bash
cp -r a11y-audit ~/.claude/skills/
```

Or symlink from a shared location. Confirm with `ls ~/.claude/skills/a11y-audit/SKILL.md`.

### Codex

Per the [Codex Agent Skills docs](https://developers.openai.com/codex/skills), skills live in one of two locations:

```bash
# User-scoped (available across all repos)
cp -r a11y-audit ~/.agents/skills/

# Repo-scoped (checked into the project, shared with the team)
cp -r a11y-audit /path/to/repo/.agents/skills/
```

Some older Codex documentation refers to `~/.codex/skills/` — that path still works in current Codex versions, but `~/.agents/skills/` is the standard per the Agent Skills specification and is cross-compatible with other agents.

Restart Codex after installation.

### Claude.ai

Download the `a11y-audit.skill` asset from the [latest GitHub Release](https://github.com/studiokicobi/a11y-skill/releases/latest) and upload it via Settings → Skills.

Prefer building from source? Run `scripts/pack.sh` at the repo root to produce a fresh `dist/a11y-audit.skill` from the unpacked tree.

## Usage

Just ask your agent:

> "Run an accessibility audit on this project."
> "Check WCAG compliance on https://staging.example.com."
> "Audit `src/components/` for a11y issues."

The skill triggers on any request mentioning accessibility, a11y, WCAG, screen readers, keyboard navigation, color contrast, ARIA, or related topics.

After the audit completes the agent will suggest the next actions for your run.
Common ones include:

> "apply the safe fixes" — agent patches what it can
> "walk me through the decisions" — agent asks you one question at a time
> "give me the checklist" — full Test-it-yourself view, including scanner-flagged manual findings and guided checks
> "show me the manual findings" — narrower view of just the scanner-flagged items that need human verification
> "save the baseline" — lock in this run as the regression reference
> "run the CI check" — re-check against the baseline on a PR

The console output highlights the recommended first step; the full report shows the complete set of next actions.

## How this is different

- **Fix autonomy comes first.** Most tools sort by severity. This skill sorts by who can fix the issue and what kind of hand-off is needed.
- **Source-aware reporting.** Runtime and stateful findings carry source-mapping confidence instead of stopping at the DOM snapshot.
- **Agent-native conversation contract.** The report and skill agree on the exact verbs the user can say next.
- **Stateful journeys, not just pages.** Findings can stay attached to the interaction step that produced them.
- **Honest coverage.** The report keeps **Test it yourself** and **Not checked** visible so a clean automated run does not overclaim accessibility.
- **One public workflow surface.** `audit` and `ci` stay the visible entry points, with the rest kept as building blocks.

## Public workflow

Most users should start with the orchestrator, not the individual scripts:

```bash
# Quick local audit of source only
python3 scripts/cli.py audit --path src/

# Quick local audit of a running site
python3 scripts/cli.py audit --url http://localhost:3000

# Full local audit with packaged artifacts
python3 scripts/cli.py audit \
  --path . \
  --url http://localhost:3000 \
  --mode full \
  --output-dir .artifacts/a11y/latest

# Full audit with explicit configs and baseline comparison
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

# Save a baseline from the public flow
python3 scripts/cli.py audit \
  --path . \
  --mode quick \
  --output-dir .artifacts/a11y/latest \
  --write-baseline .a11y/baseline.json

# CI / PR workflow
python3 scripts/cli.py ci \
  --path . \
  --url http://localhost:3000 \
  --baseline-file .a11y/baseline.json \
  --changed-files .a11y/changed-files.txt \
  --output-dir .artifacts/a11y/ci \
  --ci
```

Both commands write one artifact directory per run containing:

- `report.md`
- `report.json`
- `summary.md`
- `manifest.json`
- scanner JSON under `scanners/`
- screenshots and other evidence under `evidence/`

The top of `report.md` includes a one-line outcome summary, a snapshot of what was checked, an artifact index, and a mandatory `What to do next` block before the bucketed findings.

## Advanced invocation

The lower-level scripts remain available for debugging, fixtures, and advanced usage:

```bash
# Static scan
python3 scripts/a11y_scan.py src/ --output /tmp/static.json

# Runtime scan (auto-installs Playwright + axe-core on first use)
node scripts/a11y_runtime.js --url http://localhost:3000 --output /tmp/runtime.json

# Runtime scan with per-page config, auth, viewport, and wait settings
node scripts/a11y_runtime.js --config runtime.config.json --output /tmp/runtime.json

# Stateful journey scan with checkpoint screenshots
node scripts/a11y_stateful.js --config journey.config.json --output /tmp/stateful.json

# Token scan for supported JSON token files
python3 scripts/tokens.py design-tokens.json --output /tmp/tokens.json

# Triage into markdown plus normalized JSON
python3 scripts/triage.py --static /tmp/static.json --runtime /tmp/runtime.json --stateful /tmp/stateful.json --tokens /tmp/tokens.json --output report.md --json-output report.json

# Compare a run to an existing baseline
python3 scripts/triage.py --static /tmp/static.json --tokens /tmp/tokens.json --json-output report.json --baseline-file baseline.json

# Write a new baseline directly from triage output
python3 scripts/triage.py --static /tmp/static.json --tokens /tmp/tokens.json --json-output report.json --write-baseline baseline.json

# Or build a baseline from an existing normalized report
python3 scripts/baseline.py --report report.json --output baseline.json

# Render a CI/PR summary and use CI exit codes (summary written to <output-dir>/summary.md)
python3 scripts/cli.py ci --static /tmp/static.json --runtime /tmp/runtime.json --baseline-file baseline.json --output-dir /tmp/a11y-ci --ci

# Render a PR summary from an existing normalized report
python3 scripts/report.py --report report.json --summary-output pr-summary.md --ci

# Color contrast check
python3 scripts/contrast_checker.py --fg "#999" --bg "#fff" --suggest
```

## Report structure

The full markdown report starts with:

- one-line outcome summary
- `Snapshot`
- artifact index
- `What to do next`

Then it continues with the fix-autonomy buckets in this order:

1. **Safe to fix now** — each issue has a ready diff and the report tells the user to say "apply the safe fixes".
2. **Needs your decision** — each issue has a specific decision prompt and is handled one question at a time.
3. **Test it yourself** — split into scanner-flagged `Manual findings` and the always-generated `Guided checklist`.

Plus a "Not checked" section listing WCAG criteria that no automated tool can evaluate, so you know the gaps.

When `--json-output` is used, the normalized report includes deterministic `not_checked` findings, status and waiver metadata, `group_reason`, `fingerprint`, `fingerprint_data`, `mapping`, optional `blast_radius`, `baseline_comparison`, and `confirmed_by`.

## Baselines and waivers

The normalized JSON report is the source for repeatable regression tracking.

- Use `--write-baseline` on `cli.py audit`, `--write-baseline` on `triage.py`, or `scripts/baseline.py`, to save a stable JSON baseline.
- Use `--baseline-file` on later runs to classify findings as `new`, `unchanged`, `fixed`, `resolved`, `stale`, or `waived`.
- Static findings use stable-anchor precedence for fingerprints: `id`, `data-testid`, associated label, `name`, nearest heading, then line fallback.
- Token findings use `rule_id + file + token anchor` fingerprints so design-system issues survive line movement in the token file.
- Line-fallback fingerprints are marked `unstable: true` so a disappeared match becomes `stale` rather than being overclaimed as `fixed`.
- Use `--status-file` on `triage.py` to carry waiver and administrative status records across runs.

## Source mapping and CI mode

Runtime and stateful findings now carry a `mapping` object with confidence and explanation.

- Static findings map directly to the scanned source file and line with `high` confidence.
- Token findings map directly to the token file with `high` confidence.
- Runtime/stateful findings currently map using narrow debug-only hints:
  - `data-source-loc`
  - `data-source-file` plus `data-source-line`
  - `data-component-file` / `data-component-line`
  - `data-component-stack` values that include `path:line`
- If no mapping hints are present, runtime/stateful findings stay `low` confidence and are excluded from changed-files scoping.

`cli.py ci` adds CI-oriented behavior:

- `--changed-files` scopes the report to the listed source files using `mapping.source_file` or direct source locations.
- `--output-dir` collects the full artifact set (`report.json`, `report.md`, `summary.md`, `manifest.json`, raw scanner inputs) in one directory; `summary.md` is the GitHub-friendly PR summary.
- `--ci` returns deterministic exit codes:
  - `0` no blocking findings
  - `1` blocking findings at the configured threshold
  - `2` configuration/runtime error
  - `3` baseline error
- Default CI threshold is:
  - severity `serious` or higher
  - confidence `high`
  - when baseline is present, only `new` findings block by default
  - manual-review findings do not block unless `--fail-on-manual-findings` is set

## Runtime config

`a11y_runtime.js` accepts `--config` with JSON or YAML. Current runtime config supports:

- top-level `auth`
- top-level `defaults`
- per-page overrides in `pages[]`

Minimal auth example:

```yaml
auth:
  mode: storage_state
  storage_state_path: .secrets/playwright-auth.json
```

> **Artifact reproducibility note.** YAML runtime configs that contain an
> `auth:` block are not copied verbatim into the artifact bundle's
> `inputs/` directory — the skill ships stdlib-only and cannot parse YAML
> safely for structural redaction. A placeholder file is written instead,
> and `manifest.json` records the original source path. If you need full
> artifact reproducibility for the runtime config, use JSON
> (`runtime.config.json`), which is redacted field-by-field via a
> structural allowlist.

Per-page example:

```yaml
defaults:
  wait_until: networkidle
  timeout: 30000
  viewport:
    width: 1280
    height: 800
  reduced_motion: reduce
  route_blocklist:
    - "**/*.mp4"
    - "**/analytics/**"
pages:
  - url: http://localhost:3000/settings
    wait_for:
      selector: "[role='main']"
    screenshot: true
    screenshot_dir: .artifacts/runtime
```

## Journey config

`a11y_stateful.js` accepts `--config` with JSON or YAML. The supported shape is documented in `references/journey_schema.md`.

Minimal example:

```yaml
journeys:
  - id: modal-open-close
    start_url: /settings
    steps:
      - id: open-modal
        action: click
        selector: '[data-testid="open-settings-modal"]'
        wait_for:
          selector: '[role="dialog"]'
        scan: true
      - id: close-modal
        action: press
        key: Escape
        wait_for:
          hidden_selector: '[role="dialog"]'
        scan: true
```

## Token config

`tokens.py` currently supports one explicit JSON token format intended to stay narrow and reliable:

- `tokens`: nested token values, where leaf objects can use `{ "value": "#rrggbb" }`
- `pairs[]`: contrast pairs with `foreground`, `background`, `kind`, and optional `scope`
- `focus_indicators[]`: focus ring definitions with `token`, `background`, and optional `width_px`
- `semantic_states[]`: semantic color tokens with `token`, `meaning`, and `non_color_cue`

Minimal example:

```json
{
  "tokens": {
    "color": {
      "text": { "muted": { "value": "#9aa0aa" } },
      "surface": { "default": { "value": "#ffffff" } }
    }
  },
  "pairs": [
    {
      "id": "body-muted",
      "foreground": "color.text.muted",
      "background": "color.surface.default",
      "kind": "text",
      "scope": "design-system"
    }
  ]
}
```

## What this skill does NOT do

- It's not a replacement for testing with real assistive technology.
- It doesn't certify legal compliance (ADA, Section 508, EN 301 549, EAA).
- It doesn't redesign brand palettes when contrast failures are fundamental to the design system.

## Directory layout

```
a11y-audit/
├── SKILL.md                              # Agent-facing workflow
├── README.md                             # This file
├── scripts/
│   ├── a11y_scan.py                      # Static scanner (stdlib only)
│   ├── a11y_runtime.js                   # Runtime scanner (Playwright + axe-core)
│   ├── a11y_stateful.js                  # Stateful journey scanner (Playwright + axe-core)
│   ├── contrast_checker.py               # WCAG contrast math
│   └── triage.py                         # Scanner output → triaged report
├── references/
│   ├── triage-rules.md                   # Classification logic
│   ├── wcag-22-criteria.md               # Coverage matrix
│   ├── wcag_coverage.md                  # Deterministic not-checked source
│   ├── journey_schema.md                 # Supported journey config shape
│   ├── contrast-alternatives.md          # Curated color replacements
│   ├── pitfalls.md                       # Anti-patterns to avoid
│   ├── fix-patterns-react.md             # React / Next.js
│   ├── fix-patterns-vue.md               # Vue / Nuxt
│   ├── fix-patterns-angular.md           # Angular
│   ├── fix-patterns-svelte.md            # Svelte / SvelteKit
│   └── fix-patterns-html.md              # Plain HTML / template languages
└── assets/                               # (reserved for future)
```

## License

MIT.
