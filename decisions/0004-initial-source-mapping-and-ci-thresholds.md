# 0004: Initial Source Mapping And CI Thresholds

## Status

Accepted

## Context

Phase 4 needs explainable source mapping and deterministic CI behavior, but the repo does not yet have a robust source-map pipeline or framework-specific stack extraction. We need a narrow initial implementation that is reliable enough for CI and changed-files scoping without overstating source ownership.

## Decision

- Keep static and token findings mapped directly to their source file and line with `high` confidence.
- For runtime and stateful findings, support only explicit debug hints in the rendered DOM:
  - `data-source-loc`
  - `data-source-file` plus `data-source-line`
  - `data-component-file` / `data-component-line`
  - `data-component-stack` values that include `path:line`
- Assign `high` confidence to direct source attributes and `medium` confidence to component-hint mappings.
- Leave unmapped runtime/stateful findings at `low` confidence with an explicit explanation.
- Add `scripts/cli.py` for CI-mode orchestration and `scripts/report.py` for PR-summary rendering.
- In CI mode, default to blocking only `new` findings at severity `serious` or higher with `high` confidence when a baseline is present. Without a baseline, evaluate all open findings at that threshold.
- Keep manual-review findings non-blocking by default.

## Consequences

- Changed-files mode is reliable only for findings with direct source locations or explicit mapping hints.
- Runtime/stateful findings without debug hints remain visible in the main report but drop out of scoped CI summaries.
- The CI surface is deterministic now without requiring a full source-map implementation, and later source-map support can plug into the existing `mapping` field without changing report consumers.
