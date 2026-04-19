# Changelog

## 0.2.0 — Review response

Addressed issues surfaced in a detailed code review.

### Scanner correctness

- **Multiline tag detection fixed.** The static scanner now scans each file as
  one string rather than line-by-line for tag-oriented rules. Previously a
  `<img>` or `<div onClick>` split across multiple lines (common in real
  React/Vue formatting) would slip through entirely. The `react-multiline`
  fixture guards against regression.
- **Angular `(click)=` and Svelte `on:click=` now detected.** The clickable
  non-interactive rule previously only matched React/Vue-style `onClick` /
  `onclick`. Angular template syntax was completely uncovered. The
  `angular-template` fixture guards against regression.
- **Angular framework detection fixed for `.component.html` files.** The
  previous fallback used `Path.suffix`, which sees `.html` and returned
  `"html"` instead of `"angular"`. Framework detection now tracks the
  compound `.component.html` suffix separately.

### Runtime scanner correctness

- **Added `wcag22a` tag** to the axe-core runOnly list. Previously only
  `wcag22aa` was included, which meant WCAG 2.2 Level A-only rules were
  being skipped despite the skill claiming 2.2 coverage.
- **Process axe `incomplete` results.** The scanner was requesting incomplete
  findings but silently discarding them. They now route to Group 2 (needs
  human input) with a `(needs manual verification)` suffix and a
  `result_type: 'incomplete'` marker in `fix_data`.

### Triage correctness

- **Cross-scanner deduplication rebuilt.** The previous key was
  `(rule_id, file, line)`, which could never match across scanners because
  static reports source paths and runtime reports URLs. New dedup does a
  second pass matching by rule and element signature (tag + id/class/src/href).
  Static records win on match with a `confirmed_by_runtime: true` flag.
- **Multiline diffs produce valid unified-diff output.** The previous
  `diff()` helper emitted `- a\n- b\n+ c\n+ d` as a single prefixed line,
  which isn't valid diff format when before/after span multiple lines. Each
  line of before/after now gets its own `-` or `+` prefix.

### Docs honesty

- **SKILL.md no longer overclaims coverage.** The previous "WCAG 2.2
  coverage" section implied the scanner checked target size, dragging
  alternatives, redundant entry, and accessible authentication. In reality
  those are axe-only or manual-only. The section is now split into explicit
  "Static rules / Runtime via axe / Manual / Not checked" tiers listing each
  implemented check by WCAG criterion.
- **Spec/output drift fixed.** The output contract in SKILL.md said
  `**File**:` but triage.py emitted `**Location**:`. Contract updated to
  match the emitter. Group 3 count omission documented as intentional
  (manual checklist is a fixed list, not scanner-dependent).

### Codex support

- **Install paths updated** to `~/.agents/skills/` (user) and
  `.agents/skills/` (repo), per the current Codex Agent Skills
  specification. The older `~/.codex/skills/` path is still noted as
  working for backward compatibility.
- **`agents/openai.yaml` added** with interface metadata (display name,
  brand color, default prompt), invocation policy (`allow_implicit_invocation:
  true`), and declared Python/Node/Puppeteer/axe-core dependencies.

### Test infrastructure

- **Fixture suite added under `fixtures/`** covering five scenarios:
  `react-multiline`, `html-basic`, `angular-template`, `css-contrast`,
  `clean-code` (zero-issue baseline to catch false positives). Each fixture
  has an `expected.json` snapshot.
- **`fixtures/run_fixtures.py` runner** compares scanner output against
  snapshots and exits non-zero on any regression. Supports `--update` to
  regenerate snapshots after an intentional scanner change, and `--only
  <name>` to run a single fixture.

## 0.1.0 — Initial release

- Static scanner (Python stdlib only): 12 rules covering images, clickable
  non-interactive elements, ARIA, focus indicators, contrast, forms, lang
  attribute, autoplay, tabindex.
- Runtime scanner (Node + Puppeteer + axe-core) with auto-install of
  dependencies.
- Contrast checker with WCAG 2.2 math and curated accessible alternatives.
- Triage engine grouping findings by fix autonomy: auto-fixable, needs
  human input, manual checklist, not checked.
- Framework-specific fix pattern references for React, Vue, Angular, Svelte,
  plain HTML.
- WCAG 2.2 criteria coverage matrix and common-pitfalls reference.
