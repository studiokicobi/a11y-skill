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
