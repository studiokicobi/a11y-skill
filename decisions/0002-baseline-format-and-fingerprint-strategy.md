# 0002: Baseline Format And Fingerprint Strategy

## Status

Accepted

## Context

M5 adds repeatable comparison across accessibility audit runs. The report format already carries durable finding metadata, but regression tracking needs a separate baseline format and a fingerprint strategy that survives small source shifts without overclaiming fixes.

## Decision

- Store baselines as stable JSON written by `scripts/baseline.py` or `scripts/triage.py --write-baseline`.
- Use finding fingerprints as the record key.
- Static fingerprints use `rule_id + source_file + stable_anchor`.
- Runtime and stateful fingerprints use `rule_id + normalized_selector + page_or_step_context`.
- Static stable-anchor precedence is:
  1. `id`
  2. `data-testid`
  3. associated label text
  4. `name`
  5. nearest heading
  6. line fallback
- Mark line-fallback fingerprints as `unstable: true`.
- When an unstable baseline record disappears in a later run, classify it as `stale`, not `fixed`.
- Preserve administrative statuses separately from baseline comparison so `status` remains the durable lifecycle field and baseline comparison remains regression metadata.

## Consequences

- Small markup shifts should no longer churn stable static findings when an anchor exists.
- Baseline comparison can report `new`, `unchanged`, `fixed`, `resolved`, `stale`, and `waived` without replacing the existing status model.
- Consumers can trust `fixed` only for stable fingerprints; unstable records remain advisory.
