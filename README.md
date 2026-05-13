# a11y-skill

This repo develops the `a11y-audit` skill.

## Source of truth

The editable skill lives in `.agents/skills/a11y-audit/`.

The top-level `a11y-audit.skill` file is a packaged distribution artifact. Do not edit the archive directly; update the unpacked tree first and regenerate the archive separately when needed.

## Working validation commands

Run these from the repo root:

```bash
python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py
python3 .agents/skills/a11y-audit/scripts/a11y_scan.py .agents/skills/a11y-audit/fixtures/html-basic --quiet --output /tmp/a11y-static.json
node --check .agents/skills/a11y-audit/scripts/a11y_runtime.js
```

There is no configured repo-level `pytest` or `ruff` workflow yet.

## Fixture suite

`fixtures/run_fixtures.py` is the regression harness. It walks
`.agents/skills/a11y-audit/fixtures/<name>/`, runs the relevant scanner or
triage script, and diffs against checked-in snapshots (`expected.md`,
`expected.report.json`, `expected.runtime.json`, `expected.stateful.json`,
etc.). Snapshots must be portable across machines — keep `target` /
`issues[].file` paths in fixture inputs relative to the skill root (e.g.
`fixtures/<name>/<file>`), not absolute. The CI runner has no `.git` above
`/Users/colin/`, so absolute host paths leak through `_repo_relative_path` and
fail the comparison.

Flags worth knowing:

```bash
# Default: static fixtures only (~5s, no network)
python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py

# Run one fixture
python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py --only aria-hidden-spaced-quoted

# Regenerate snapshots after an intentional scanner change
python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py --update

# Include live Playwright fixtures (real Chromium + axe-core injection)
python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py --live-runtime
```

### Live runtime — cold vs warm install

The first `--live-runtime` invocation seeds
`.agents/skills/a11y-audit/.a11y-audit-deps/` with the pinned `playwright`,
`axe-core`, and `yaml` packages, then downloads Chromium into the cache. You'll
see two markers in stderr:

```
Installing required packages: playwright@…, axe-core@…
Installing Playwright Chromium browser…
```

Subsequent runs reuse the cache and stay silent. To re-exercise the cold path
locally:

```bash
rm -rf .agents/skills/a11y-audit/.a11y-audit-deps
python3 .agents/skills/a11y-audit/fixtures/run_fixtures.py --live-runtime
```

If you're touching `scripts/a11y_runtime*.js` or `scripts/a11y_stateful.js`,
do a cold pass — the runtime bootstrap (`ensureDeps`,
`ensurePlaywrightBrowser`, `PLAYWRIGHT_BROWSERS_PATH` wiring) only matters on a
cold cache and isn't exercised by warm runs.

## CI workflow

[`.github/workflows/runtime-verify.yml`](.github/workflows/runtime-verify.yml)
runs two jobs:

- **Static fixture suite** — fast, no network. Same as `run_fixtures.py` above.
- **Live runtime + cold/warm install** — deletes the dep cache, runs
  `--live-runtime` cold (must trigger an install), then runs it again warm
  (must NOT trigger an install). Catches upstream drift in Playwright /
  Chromium / axe-core that no code-change trigger would fire.

Triggers: weekly schedule (Monday 12:00 UTC), `workflow_dispatch`, and PRs
that touch `scripts/a11y_runtime*.js`, `scripts/a11y_stateful.js`,
`fixtures/runtime-*/**`, `fixtures/stateful-*/**`, or the workflow itself.

To trigger manually:

```bash
gh workflow run runtime-verify.yml
gh run watch
```
