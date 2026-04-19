# 0003: Explicit JSON Token Schema For Phase 3

## Status

Accepted

## Context

Phase 3 adds design-system analysis, but broad token parsing would force unreliable heuristics too early. Focus indicator checks and color-only semantic checks especially need explicit meaning and usage metadata, not just raw color extraction.

## Decision

- Add a dedicated `scripts/tokens.py` scanner instead of folding token logic into `a11y_scan.py`.
- Support one explicit JSON token schema first.
- The first supported shape includes:
  - `tokens` for nested token values
  - `pairs[]` for contrast pairs
  - `focus_indicators[]` for focus ring token definitions
  - `semantic_states[]` for semantic color tokens and whether they include a non-color cue
- Treat token findings as scanner `token` in the normalized report.
- Include optional `blast_radius` metadata on token findings so reports distinguish one component, one file, and design-system-wide issues.

## Consequences

- Phase 3 stays narrow and reliable.
- Token analysis is immediately useful for curated design-token sources, but not yet for arbitrary theme files.
- Broader theme parsing can be added later without changing the token finding model or the triage/report pipeline.
