# a11y-audit

WCAG 2.2 Level AA accessibility audit skill for Claude Code, Codex, and other agent runtimes.

Produces a **triaged report grouped by fix autonomy** — auto-fixable, needs your input, manual checklist — rather than a flat severity-sorted list. This matches how a human-plus-agent workflow actually proceeds: the agent patches what it can on approval, drafts what needs a decision, and hands off what requires assistive-tech testing.

## What it checks

- **Static analysis** of source files (Python, no dependencies): missing `alt`, `<div onClick>`, hardcoded low-contrast colors, missing labels, `outline: none` without replacement, redundant ARIA, positive `tabindex`, `aria-hidden` on focusable elements, and more.
- **Runtime analysis** via Puppeteer + axe-core today (Playwright migration is planned in a later milestone): computed color contrast, focus management as rendered, ARIA state after hydration, landmark regions, live regions, heading order.
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

# Runtime scan (auto-installs puppeteer + axe-core on first use)
node scripts/a11y_runtime.js --url http://localhost:3000 --output /tmp/runtime.json

# Triage into markdown plus normalized JSON
python3 scripts/triage.py --static /tmp/static.json --runtime /tmp/runtime.json --output report.md --json-output report.json

# Color contrast check
python3 scripts/contrast_checker.py --fg "#999" --bg "#fff" --suggest
```

## Report structure

The output is markdown with three sections in this order:

1. **Auto-fixable** — each issue has a ready diff. Reply "go" and the agent applies them.
2. **Needs your input** — each issue has a specific decision prompt. The agent drafts the fix after you answer.
3. **Manual checklist** — keyboard nav, screen reader, visual/motion, forms, cognitive. You must test these yourself.

Plus a "Not checked" section listing WCAG criteria that no automated tool can evaluate, so you know the gaps.

When `--json-output` is used, the normalized report includes deterministic `not_checked` findings, status and waiver metadata, `group_reason`, `fingerprint`, and `confirmed_by`.

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
│   ├── a11y_runtime.js                   # Runtime scanner (Puppeteer + axe-core)
│   ├── contrast_checker.py               # WCAG contrast math
│   └── triage.py                         # Scanner output → triaged report
├── references/
│   ├── triage-rules.md                   # Classification logic
│   ├── wcag-22-criteria.md               # Coverage matrix
│   ├── wcag_coverage.md                  # Deterministic not-checked source
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
