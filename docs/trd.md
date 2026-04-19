# Accessibility Audit Skill — Technical Requirements

**Version**: 2.1.1
**Last updated**: 2026-04-18
**Status**: draft for review

## 1. Purpose

Build the strongest single-package accessibility audit skill for agentic coding workflows.

The product should combine:

* fast portable static analysis
* rendered runtime analysis
* stateful interaction testing
* assisted manual review
* fix-autonomy triage
* source-aware remediation guidance
* regression tracking for CI and pull requests

The core differentiator remains unchanged:

**Findings are grouped by who can act on them next**

1. agent can safely fix now
2. agent needs a decision or missing content
3. human must manually test or verify

Fix-autonomy is the primary workflow axis; severity is secondary metadata for urgency and scheduling.

This document defines what is required to implement that vision.

---

## 2. Product Goals

### Primary goals

* Detect meaningful accessibility issues across source code, rendered DOM, and interactive flows.
* Produce reports optimized for AI-assisted remediation, not just human reading.
* Make safe fixes easy to apply and unsafe fixes impossible to auto-apply by default.
* Support common frontend stacks with minimal project setup.
* Enable repeatable audits in local development, Codex/Claude workflows, and CI.

### Secondary goals

* Reduce false positives through framework-aware parsing and confidence scoring.
* Generate guided manual test scripts for keyboard and assistive technology review.
* Track regressions over time using fingerprints and baselines.
* Surface design-system-level issues, not just page-local issues.

### Non-goals for first major version

* Perfect automatic WCAG coverage.
* Full mobile-native accessibility auditing.
* PDF remediation.
* Full legal/compliance certification workflow.
* Replacing expert human accessibility review.
* Comprehensive internationalization auditing beyond page-level `<html lang>` detection. WCAG 3.1.2 (language of parts), RTL correctness, direction attribute handling, and hreflang checks are deferred past v1.0.

---

## 3. Target Users

### Primary users

* solo builders using Codex or Claude Code
* frontend engineers working on React, Next.js, Vue, Angular, Svelte, Astro, or plain HTML
* agencies auditing client sites
* teams adding accessibility checks to CI

### Secondary users

* product designers validating design-system accessibility
* QA engineers running guided keyboard and screen reader checks
* technical leads triaging remediation work across repos

---

## 4. Core Principles

1. **Agent-first remediation**
   Reports must map directly to the next action an agent or human can take.

2. **Progressive certainty**
   The tool should auto-fix only when confidence is high.

3. **Multiple evidence layers**
   Static, runtime, flow-based, and manual findings should reinforce each other.

4. **Honest coverage**
   The tool must clearly separate automated coverage from manual-only criteria.

5. **Portable by default**
   Static checks should run with minimal dependencies; heavier modes should install only when needed.

6. **Framework-aware but not framework-bound**
   The system should adapt to framework syntax without hard coupling to one ecosystem.

---

## 5. Feature Pillars

### Pillar A — Static Source Analysis

Use whole-file source scanning for portable detection of common accessibility defects.

#### Required capabilities

* whole-file matching, not line-only matching
* framework-aware patterns for:

  * HTML
  * React / JSX / TSX
  * Vue
  * Angular templates
  * Svelte
* detection of common source-level issues including:

  * missing `lang`
  * missing `alt`
  * placeholder-as-label
  * click handlers on non-interactive elements
  * keyboard activation gaps
  * redundant ARIA roles
  * `target="_blank"` without safe `rel`
  * positive `tabindex`
  * duplicate IDs where statically visible
  * aria-hidden focusable descendants
  * icon-only controls missing accessible name
* framework-aware fix templates
* rule metadata including:

  * WCAG mapping
  * confidence
  * autofix safety level
  * required user input fields

#### Technical requirements

* Python stdlib-only base scanner remains supported
* optional parser-backed mode can be added later for higher-confidence framework parsing
* output must be structured JSON with normalized issue schema

---

### Pillar B — Runtime DOM Analysis

Use rendered-page analysis to catch issues source scanning cannot reliably detect.

The runtime implementation is moving from Puppeteer-based execution to Playwright as the single supported browser automation layer.

#### Required capabilities

* Playwright-based page loading
* axe-core integration
* support for Chromium at minimum; Firefox/WebKit optional later
* scan current page state and scoped regions
* classify `violations`, `incomplete`, and `passes` separately
* preserve original runtime rule IDs as `origin_rule_id` so triage safety is not collapsed when runtime findings are normalized
* detect heading-order anomalies at the rendered-page level (across components, after hydration)
* capture evidence:

  * URL
  * selector / target nodes
  * DOM snippet
  * screenshot path when useful
  * axe help URL if available

#### Technical requirements

* runtime rules must not be blindly remapped into static rule buckets when fix safety differs
* `incomplete` findings must be routed to decision/manual review, not discarded
* support authenticated targets through configurable headers, cookies, or Playwright storage state
* support per-page configuration: wait conditions, timeouts, route blocking, viewport, reduced motion

Minimal auth config shape:

```yaml
auth:
  mode: storage_state
  storage_state_path: .secrets/playwright-auth.json
```

Auth requirements:

* secrets must come from env vars or external secret files, not committed literals
* the skill must never log secret values
* missing or invalid auth material must fail with a redacted, actionable error

---

### Pillar C — Stateful Interaction Audits

Audit accessibility after interaction, not just on first paint.

#### Required capabilities

* run scripted user journeys using Playwright
* support page states such as:

  * open menu
  * open modal
  * validate form
  * navigate SPA route
  * reveal accordion/tab/popup
  * complete multistep checkout or onboarding step
* run axe after each state change
* record focus transitions and failures between states
* capture dynamic announcements where practical

#### Technical requirements

* journey definition format in YAML or JSON
* each journey step supports:

  * action type (`click`, `press`, `fill`, `select`, `navigate`, `assert`)
  * selector strategy
  * wait condition
  * optional scan checkpoint
* each checkpoint must produce state-specific issue sets and screenshots
* failures must identify the step where the issue surfaced
* stateful findings must carry the originating `journey_step_id`

Minimal journey config example:

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

#### Nice-to-have later

* automatic exploration for common widgets
* heuristic state discovery for menus/dialogs

---

### Pillar D — Assisted Manual Review

Add guided manual checks inspired by fast-pass and quick-assess workflows.

#### Required capabilities

* generate a short assisted review lane for each page/flow
* include structured checklists for:

  * keyboard tab order
  * focus visibility
  * escape / trap behavior for overlays
  * screen reader heading outline
  * form field announcements
  * dynamic status message announcements
  * zoom / reflow / text spacing
  * reduced motion
  * use of color only
* provide exact test steps and expected outcomes
* distinguish manual tasks that require:

  * browser only
  * keyboard only
  * screen reader
  * visual inspection

#### Technical requirements

* manual test items must be generated from page type and components present
* output format must support checkboxes and optional pass/fail notes
* manual items should map to WCAG criteria and component types

#### Future extension

* separate scripts for VoiceOver, NVDA, JAWS, and TalkBack
* expected spoken announcements for common component patterns

---

### Pillar E — Fix-Autonomy Triage Engine

This is the core product differentiator and must remain the main organizing layer.

#### Required output groups

1. **Auto-fixable** — safe to patch with high confidence
2. **Needs input** — requires content, design intent, product decision, or lower-confidence mapping
3. **Manual review** — requires human testing or verification
4. **Not checked / outside scope** — criteria not evaluated by this run

#### Population rule for "not checked"

The `not_checked` group must be populated from a fixed, declared list maintained by the skill, not from whichever criteria the scanner happened to skip. This prevents two runs from producing different "not checked" sections depending on which files were present. Specifically:

* the skill ships a `references/wcag_coverage.md` listing every WCAG 2.2 Level A and AA criterion and marking each as `static | runtime | stateful | manual-template | out-of-scope`
* criteria marked `out-of-scope` (for example 1.2.* time-based media, 2.3.1 seizure thresholds, 3.1.3 reading level) always appear in the `not_checked` group regardless of what ran
* criteria marked `manual-template` that were not included in the run's manual checklist also appear in `not_checked`
* criteria that were attempted but returned axe `incomplete` go to `needs_input`, not `not_checked`

#### Classification inputs

* scanner origin: static / runtime / stateful / manual template
* rule metadata
* standardized severity metadata: `minor | moderate | serious | critical | n/a`
* confidence score
* fix safety level
* whether missing information blocks remediation
* whether assistive technology verification is required

#### Technical requirements

* triage must be context-aware, not rule-name-only
* one rule may classify differently depending on evidence source
* severity must never override fix-autonomy grouping; it is urgency metadata only
* every finding must include a reason for its group assignment
* every autofixable finding must have a proposed patch or explicit reason no patch could be generated

#### Fix safety levels

* **safe**: deterministic structural fix, minimal semantic risk
* **guarded**: draft patch possible but requires user review
* **input-required**: cannot proceed without human decision
* **manual-only**: no patch should be attempted

---

### Pillar F — Source Mapping and Confidence

Map runtime findings back to likely source locations when possible.

#### Required capabilities

* associate runtime DOM nodes with likely source files using:

  * source maps where available
  * framework component stack traces where available
  * DOM attribute heuristics
  * design-system component signatures
* assign mapping confidence score
* avoid claiming exact source ownership without sufficient evidence

#### Technical requirements

* confidence bands: high / medium / low
* low-confidence mappings remain informational and should not enter safe autofix
* mapping explanation must be included in machine-readable output
* initial implementation should start with one or two concrete techniques:

  * source maps for mapped bundles/pages
  * framework component stacks or debug attributes when exposed in development builds

---

### Pillar G — Design System and Token Analysis

Detect systemic accessibility issues at the design layer.

#### Required capabilities

* inspect theme files and token definitions when present
* analyze color pairs for:

  * text contrast
  * large text contrast
  * UI component contrast
  * focus indicator contrast
* flag risky token patterns such as:

  * gray-on-gray text scales
  * missing focus ring tokens
  * color-only status semantics
* detect component primitives likely to cause repeated issues:

  * icon button without label support
  * unstyled links disguised as buttons
  * modal/dialog without focus management hooks

#### Technical requirements

* standalone contrast engine with accessible alternative suggestions
* preserve design intent where possible by suggesting nearby compliant colors
* token-aware reporting should identify issue blast radius: one component, one file, design system wide
* Phase 3 token analysis starts narrow: color contrast pairs, focus indicator tokens, and color-only semantic tokens only

---

### Pillar H — Baselines, Fingerprints, and Regression Tracking

Make the tool useful in CI and for ongoing improvement.

#### Required capabilities

* generate normalized issue fingerprints
* compare current run to saved baseline
* report:

  * new issues
  * resolved issues
  * unchanged issues
  * suppressed/waived issues
* support waiver file with reason and expiration

#### Technical requirements

* fingerprint strategy must be explicit:

  * static findings: `rule_id + source_file + stable_anchor`
  * runtime/stateful findings: `rule_id + normalized_selector + page_or_step_context`
* stable anchor precedence (first available wins):

  1. `id` attribute on the element
  2. `data-testid` or equivalent explicit test anchor
  3. associated `<label>` text for form controls
  4. `name` attribute
  5. nearest enclosing heading text
  6. if none of the above are present, fall back to line number and mark the fingerprint `unstable: true` in the baseline record so reviewers know it may drift on unrelated edits
* stable anchors should prefer IDs, names, associated labels, or nearby stable text over raw line numbers when available
* fingerprint should survive small markup shifts where possible
* baseline format must be stable JSON
* CI mode must support non-zero exit on new high-confidence issues
* report mode must support markdown and machine-readable JSON

---

### Pillar I — Repository and CI Integration

Support ongoing team workflows.

#### Required capabilities

* run locally via skill command
* run in CI via scriptable interface
* output GitHub-friendly markdown summary
* optionally generate issue or PR comment content
* support changed-files-only mode for pull requests

#### Technical requirements

* CLI arguments for:

  * target path or URL
  * scan mode
  * framework override
  * output paths
  * baseline path
  * journey config path
  * auth config path
* deterministic exit codes for CI:

  * `0` — success: no findings above threshold
  * `1` — findings above configured threshold
  * `2` — configuration or runtime error (bad CLI args, unreachable target, auth failure, missing required file)
  * `3` — baseline stale, corrupt, or schema-incompatible with current scanner version
* no interactive prompts in CI mode
* CI failure knobs must be configurable with documented defaults:

  * default: fail on new `serious` or `critical` findings with `high` confidence
  * optional knobs: fail-on-severity threshold, fail-on-confidence threshold, fail-on-any-new, fail-on-manual-findings=false by default

---

## 6. System Architecture

## 6.1 High-level modules

* `scanner_static`
* `scanner_runtime`
* `scanner_stateful`
* `triage_engine`
* `source_mapper`
* `token_analyzer`
* `manual_review_generator`
* `baseline_engine`
* `report_renderer`
* `cli_orchestrator`

## 6.2 Data flow

1. detect project/framework
2. run selected scanners
3. normalize findings into common schema
4. enrich with WCAG metadata and mapping confidence
5. deduplicate and fingerprint
6. classify by fix autonomy
7. generate patches where allowed
8. render outputs:

   * markdown report
   * JSON report
   * optional CI summary

## 6.3 Deduplication rules

* dedupe across static and runtime where evidence points to same issue
* preserve stronger evidence if duplicates exist
* prefer source-aware finding over generic runtime finding when confidence is high
* retain links to all evidence sources in merged finding

---

## 7. Normalized Finding Schema

```json
{
  "id": "string",
  "rule_id": "string",
  "origin_rule_id": "string",
  "title": "string",
  "wcag": ["1.1.1"],
  "severity": "minor|moderate|serious|critical|n/a",
  "scanner": "static|runtime|stateful|manual-template|token",
  "scanner_version": "string",
  "detected_at": "ISO-8601 timestamp",
  "triage_group": "autofix|needs_input|manual_review|not_checked",
  "fix_safety": "safe|guarded|input-required|manual-only",
  "confidence": "high|medium|low",
  "status": "open|waived|resolved|fixed|stale",
  "group_reason": "string",
  "waiver": {
    "reason": "string",
    "approved_by": "string",
    "expires_at": "ISO-8601 timestamp"
  },
  "location": {
    "file": "string",
    "line": 0,
    "column": 0,
    "url": "string",
    "selector": "string",
    "journey_step_id": "string"
  },
  "mapping": {
    "source_file": "string",
    "source_line": 0,
    "confidence": "high|medium|low",
    "explanation": "string"
  },
  "evidence": {
    "snippet": "string",
    "dom_snippet": "string",
    "screenshot": "string",
    "axe_help_url": "string"
  },
  "decision_required": {
    "question": "string",
    "options": ["string"]
  },
  "proposed_fix": {
    "kind": "diff|instruction|none",
    "diff": "string",
    "notes": "string"
  },
  "fingerprint": "string",
  "confirmed_by": ["static", "runtime", "stateful", "manual-template", "token"]
}
```

Schema conventions:

* **Severity vocabulary** is fixed across the system: `minor | moderate | serious | critical | n/a`.
* **WCAG references** use dotted success criterion numbers only (e.g. `"1.1.1"`, `"2.4.11"`), without version prefix. WCAG version is implicit from the scanner's coverage metadata rather than repeated per finding.
* **`rule_id`** is the skill's normalized rule identifier used for triage and dedup.
* **`origin_rule_id`** is the underlying scanner's own identifier (e.g. axe-core's `color-contrast`) preserved so triage rules can distinguish runtime findings from structurally similar static ones. Omit when the finding originates from the skill's own static rules.
* **`screenshot` paths** are relative to the report output directory, not absolute.
* **`group_reason`** is a required plain-language explanation of why the finding landed in its triage group or status section.
* **`status`** defaults to `open` for new findings.

  * `open` — currently active, surfaced in its triage group
  * `waived` — administratively accepted; carries a `waiver` object and appears in the report's waiver section, not the active-issue groups
  * `fixed` — the finding disappeared in a later scan because the underlying code or content changed (no matching fingerprint in the current run)
  * `resolved` — administratively closed after human review, with no code change required (for example, a false positive confirmed by the team); does not require a matching current finding
  * `stale` — the fingerprint no longer matches any current DOM or source location, but there is no evidence of an intentional fix; treat as advisory, re-scan to confirm
* **`waiver`** — omit the field entirely, or set it to `null`, unless `status = waived`. Implementations must not emit an empty `waiver` object for non-waived findings.
* **`waiver.expires_at`** — once passed, the finding reverts to `open` in the next run.

---

## 8. Output Requirements

### Markdown report

Must include:

* target and scan metadata
* coverage summary
* grouped findings by fix autonomy
* issue counts by source and confidence
* actionable diffs for safe fixes
* decision prompts for input-required items
* guided manual checklist
* not-checked section
* regression summary when baseline is present

### JSON report

Must include all normalized findings, scanner metadata, baseline comparison, and coverage metadata.

### Optional artifacts

* screenshots
* DOM snapshots
* focus-order log
* generated Playwright state checkpoints

---

## 9. Modes

### Mode 1 — Quick audit

* static scan
* runtime scan on one entry page
* short manual checklist
* no journeys

### Mode 2 — Full audit

* static scan
* runtime scan across configured pages
* stateful journeys
* full manual checklist
* token analysis
* baseline comparison

### Mode 3 — Fix mode

* generate and optionally apply safe patches
* produce decision queue for unresolved items
* rerun targeted checks after patching

### Mode 4 — CI mode

* non-interactive
* changed-files mode where applicable
* baseline comparison
* machine-readable output
* fail build based on configurable thresholds

---

## 10. Functional Requirements by Phase

### Pillar → Phase mapping

| Pillar | Phase |
| --- | --- |
| A. Static Source Analysis | Phase 1 (stabilize existing v0.2 implementation) |
| B. Runtime DOM Analysis | Phase 1 (Puppeteer → Playwright migration), Phase 2 (auth) |
| C. Stateful Interaction Audits | Phase 2 |
| D. Assisted Manual Review | Phase 2 |
| E. Fix-Autonomy Triage Engine | Phase 1 (core), incremental improvements each phase |
| F. Source Mapping and Confidence | Phase 4 |
| G. Design System and Token Analysis | Phase 3 (narrow scope), expansion later |
| H. Baselines, Fingerprints, Regression | Phase 3 |
| I. Repository and CI Integration | Phase 4 |

CI mode (Mode 4) is usable from Phase 3 onward using baselines and fingerprints alone; source mapping in Phase 4 is an enhancement that improves the PR-comment output, not a prerequisite for CI to function.

## Phase 1 — Stabilize core auditor

Required:

* fix runtime-vs-static triage safety model
* wrapped-label support
* unique ID generation for generated label fixes
* conservative redundant-role handling
* improved diff generation and merge behavior
* fixture suite expansion

Acceptance:

* zero known mis-triaged safe fixes in core fixture set
* static/runtime dedup works on representative cases
* markdown and JSON outputs stable

## Phase 2 — Guided manual and stateful flows

Required:

* journey config format
* Playwright checkpoint scans
* focus tracking
* assisted checklist generator
* screenshots per checkpoint
* minimal auth config support for stateful and authenticated runtime scans

Acceptance:

* modal, form validation, and SPA navigation fixtures supported
* reports clearly separate page-load from post-interaction findings

## Phase 3 — Design-system and regression intelligence

Required:

* token analysis limited to contrast, focus-indicator, and color-only semantic checks
* contrast suggestion engine
* use-of-color heuristics
* baseline and fingerprint engine
* waiver support

Acceptance:

* new vs existing issues shown reliably across repeated runs
* token-level contrast findings identify blast radius

## Phase 4 — Source mapping and workflow integration

Required:

* source-map-aware mapping
* confidence scoring
* GitHub/PR summary renderer
* changed-files mode
* authenticated scanning support

Acceptance:

* runtime findings map back to source with explainable confidence
* CI mode usable in real repositories without interactive steps

---

## 11. Test Strategy

### Unit tests

* rule-level static detection
* triage classification
* diff generation
* fingerprint generation
* contrast calculations

### Fixture tests

Need fixtures for:

* multiline JSX and HTML
* wrapped labels
* Angular `(click)` and Svelte `on:click`
* duplicate IDs
* target blank rel merge
* modal/dialog focus traps
* SPA route change announcements
* form validation errors
* token contrast failures
* runtime-only issues with no static source match

### Integration tests

* end-to-end audit on sample apps across frameworks
* Playwright stateful flow tests
* baseline comparison across two runs
* CI exit-code tests

### Quality metrics

* false-positive rate on curated fixture repo
* autofix precision for safe fixes
* successful dedup rate across scanners
* mapping confidence accuracy on sampled runtime findings

---

## 12. Performance Requirements

### Sizing definitions

* **Small project** — under 1,000 source files; single entry page for runtime scan
* **Small-to-medium site** — under 20 pages; up to 3 journeys averaging 5 steps each
* **Large** — anything above; performance targets here are best-effort, not contractual

### Quick audit target

* complete under 30 seconds on a **small project** (static scan + single runtime page + short manual checklist)
* the 30-second target excludes cold browser installation; first-run Playwright install is measured and reported separately

### Full audit target

* complete under 5 minutes on a **small-to-medium site** with configured flows
* target assumes a warm browser cache and sequential journey execution; parallelism is a later optimization

### Constraints

* static scan should remain fast enough for local iterative use (target: under 5 seconds on a small project)
* runtime mode should cache browser/tool setup when possible
* screenshots and DOM snapshots should be optional in quick mode
* on codebases exceeding the "large" threshold, the static scanner must stream results incrementally rather than buffering all findings in memory

---

## 13. Safety and Trust Requirements

* never auto-apply content decisions such as alt text semantics without input
* never auto-classify runtime contrast failures as safe code fixes without source-confidence and fix-confidence support
* clearly label inferred source mappings as inferred
* report unsupported criteria explicitly
* maintain machine-readable audit provenance for each finding

---

## 14. Suggested Repository Structure

In this repo, `.agents/skills/a11y-audit/` is the editable source tree. The top-level `a11y-audit.skill` file is a distributable artifact and should be regenerated from the unpacked tree rather than edited directly.

```text
.agents/skills/a11y-audit/
  SKILL.md
  README.md
  agents/
    openai.yaml
  scripts/
    a11y_scan.py
    a11y_runtime.js
    a11y_stateful.js
    triage.py
    tokens.py
    baseline.py
    report.py
    cli.py
  references/
    wcag_coverage.md
    framework_patterns.md
    manual_test_protocols.md
    journey_schema.md
  fixtures/
    html-basic/
    react-multiline/
    wrapped-label/
    angular-events/
    svelte-events/
    modal-dialog/
    spa-route-change/
    token-contrast/
  tests/
    test_static.py
    test_triage.py
    test_runtime.py
    test_stateful.py
```

---

## 15. Open Design Decisions

The implementation should resolve these before Phase 2 begins:

* whether to stay regex-first long term or adopt parser-backed modes per framework
* whether screenshots are always-on for runtime issues or conditional
* whether source mapping is core or optional advanced mode
* how much of manual review generation is generic versus component-aware
* whether to support both markdown-only reports and interactive HTML reports

Once a decision is made, record it in `decisions/NNNN-short-slug.md` with the date, the options considered, the chosen option, and the rationale. The decisions log is the canonical record of *why* things are the way they are; code comments and PR descriptions are not durable enough.

---

## 16. Definition of Success

The tool will be considered successful when it can:

* audit a real repo with minimal setup
* catch source-level, runtime, and interaction-state issues
* safely auto-fix a meaningful subset of problems
* ask targeted questions for ambiguous findings
* generate a useful manual review lane
* track regressions across runs
* produce outputs that are equally useful in Codex, Claude Code, and CI

---

## 17. Immediate Next Steps

1. implement the v2.1 stabilization fixes in the current repo
2. add JSON schema for normalized findings
3. define journey configuration format and ship the first example config
4. add minimal auth configuration support for authenticated runtime/stateful scans
5. add first stateful fixtures: modal, form validation, route transition
6. lock baseline fingerprint design for static and runtime/stateful findings
7. draft manual-review protocol templates
8. choose Phase 2 milestone and acceptance tests

---

## Appendix A — TRD → v0.2 implementation mapping

The current v0.2 skill already implements part of this TRD. This table gives implementers a starting point so they don't rebuild what exists.

| Pillar | v0.2 status | Gap to close |
| --- | --- | --- |
| A. Static Source Analysis | **Built** — 12 rules, whole-file scanning, Python stdlib only, multi-framework patterns including Angular `(click)=` and Svelte `on:click=` | Add `origin_rule_id` field; add wrapped-label detection; add duplicate-id rule; add icon-only-control rule; add stable-anchor extraction for fingerprinting |
| B. Runtime DOM Analysis | **Built on Puppeteer** — axe-core integration, violation + incomplete result processing, `wcag2a/aa/21a/21aa/22a/22aa/best-practice` tag set | Rewrite on Playwright; add heading-order rule routing; add auth config support; add scoped-region scanning; add per-page configuration |
| C. Stateful Interaction Audits | **Not built** | Full implementation: journey config parser, step executor, per-checkpoint axe runs, focus transition recording, `journey_step_id` propagation |
| D. Assisted Manual Review | **Partial** — static manual checklist exists in triage output | Generate checklist from page type and detected components rather than a fixed template; mark required capability (browser / keyboard / screen reader / visual) per item |
| E. Fix-Autonomy Triage | **Built** — four groups, safety levels, scanner-origin classification, cross-scanner dedup with `confirmed_by` flag | Add `status` and `waiver` handling; add "not checked" population from fixed WCAG coverage list; add reason-for-group-assignment field |
| F. Source Mapping | **Not built** | Phase 4; start with source maps and component stack traces only |
| G. Token Analysis | **Partial** — contrast checker script exists for hex and Tailwind classes | Add theme file parsing; expand to focus-indicator and color-only semantic checks; add blast-radius reporting |
| H. Baselines and Fingerprints | **Not built** | Phase 3; see Pillar H in section 5 for fingerprint rules |
| I. CI Integration | **Partial** — CLI exit codes exist for scan success/failure | Add changed-files mode; add GitHub PR summary renderer; add exit codes 2 and 3; add waiver file support |

---

## Appendix B — Versioning

| Version | Date | Notes |
| --- | --- | --- |
| 2.1.1 | 2026-04-18 | Clarified `resolved` vs `fixed` status semantics; made `waiver` field nullability explicit; fixed section reference in Appendix A |
| 2.1 | 2026-04-18 | Added stable-anchor precedence, waiver/status schema fields, CI exit codes, performance sizing, pillar-to-phase mapping, i18n non-goal, v0.2 mapping appendix |
| 2.0 | prior | Severity reconciliation, journey config example, fingerprint strategy split, auth minimal shape, token scope narrowed, source mapping narrowed, schema additions (`scanner_version`, `detected_at`, `confirmed_by`, `journey_step_id`) |
| 1.0 | initial | First draft |
