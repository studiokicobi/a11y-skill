# a11y-audit

WCAG 2.2 Level AA accessibility audit skill for Claude Code, Codex, and other agent runtimes.

Produces a **triaged report grouped by fix autonomy** — auto-fixable, needs your input, manual checklist — rather than a flat severity-sorted list. This matches how a human-plus-agent workflow actually proceeds: the agent patches what it can on approval, drafts what needs a decision, and hands off what requires assistive-tech testing.

## What it checks

- **Static analysis** of source files (Python, no dependencies): missing `alt`, `<div onClick>`, hardcoded low-contrast colors, missing labels, `outline: none` without replacement, redundant ARIA, positive `tabindex`, `aria-hidden` on focusable elements, and more.
- **Runtime analysis** via Playwright + axe-core: computed color contrast, focus management as rendered, ARIA state after hydration, landmark regions, live regions, heading order, and axe incomplete results routed to manual/input review.
- **Stateful journey analysis** via Playwright + axe-core checkpoints: post-interaction findings tagged with `journey_step_id`, focus transitions, step failures, and screenshots per audited state.
- **WCAG 2.2** coverage including the new criteria: 2.4.11 Focus Appearance, 2.5.7 Dragging Movements, 2.5.8 Target Size, 3.3.7 Redundant Entry, 3.3.8 Accessible Authentication.

Automated tools catch roughly 30–40% of accessibility issues. This skill is honest about that — the manual checklist covers what the scanners can't reach.

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

Upload the `.skill` archive via Settings → Skills.

## Usage

Just ask your agent:

> "Run an accessibility audit on this project."
> "Check WCAG compliance on https://staging.example.com."
> "Audit `src/components/` for a11y issues."

The skill triggers on any request mentioning accessibility, a11y, WCAG, screen readers, keyboard navigation, color contrast, ARIA, or related topics.

## Manual invocation

The scripts are usable directly:

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

# Render a CI/PR summary and use CI exit codes
python3 scripts/cli.py --static /tmp/static.json --runtime /tmp/runtime.json --baseline-file baseline.json --pr-summary-output pr-summary.md --ci

# Render a PR summary from an existing normalized report
python3 scripts/report.py --report report.json --summary-output pr-summary.md --ci

# Color contrast check
python3 scripts/contrast_checker.py --fg "#999" --bg "#fff" --suggest
```

## Report structure

The output is markdown with three sections in this order:

1. **Auto-fixable** — each issue has a ready diff. Reply "go" and the agent applies them.
2. **Needs your input** — each issue has a specific decision prompt. The agent drafts the fix after you answer.
3. **Manual checklist** — capability-tagged assisted checks derived from the page and journey context. You must test these yourself.

Plus a "Not checked" section listing WCAG criteria that no automated tool can evaluate, so you know the gaps.

When `--json-output` is used, the normalized report includes deterministic `not_checked` findings, status and waiver metadata, `group_reason`, `fingerprint`, `fingerprint_data`, `mapping`, optional `blast_radius`, `baseline_comparison`, and `confirmed_by`.

## Baselines and waivers

The normalized JSON report is the source for repeatable regression tracking.

- Use `--write-baseline` on `triage.py`, or `scripts/baseline.py`, to save a stable JSON baseline.
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

`cli.py` adds CI-oriented behavior:

- `--changed-files` scopes the report to the listed source files using `mapping.source_file` or direct source locations.
- `--pr-summary-output` writes GitHub-friendly markdown.
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
