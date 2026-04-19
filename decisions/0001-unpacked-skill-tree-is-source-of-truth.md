# 0001 — Unpacked skill tree is the source of truth

Date: 2026-04-18

## Context

The repo contains both an unpacked skill tree at `.agents/skills/a11y-audit/` and a packaged archive at `a11y-audit.skill`.

Baseline inspection found that editing and validating the archive directly makes repo commands, paths, and validation behavior harder to reason about. It also creates drift between the installed skill tree and the packaged artifact.

## Options considered

1. Treat `a11y-audit.skill` as the primary source and unpack it only for inspection.
2. Treat `.agents/skills/a11y-audit/` as the primary source and regenerate `a11y-audit.skill` from it when packaging is needed.

## Decision

Treat `.agents/skills/a11y-audit/` as the editable source of truth for code, fixtures, references, and skill metadata.

Treat `a11y-audit.skill` as a distributable artifact that is regenerated from the unpacked tree.

## Rationale

- The unpacked tree matches the path layout described by the TRD.
- Validation commands can run directly against real files without temporary extraction.
- Milestone work is clearer when scripts, fixtures, and references live in a normal directory structure.
- This reduces drift between repo docs, local validation, and the installed skill layout.

## Consequences

- Repo-level docs and commands should point to `.agents/skills/a11y-audit/`.
- Changes should be made in the unpacked tree first.
- Packaging or archive refresh should be treated as a separate explicit step.
