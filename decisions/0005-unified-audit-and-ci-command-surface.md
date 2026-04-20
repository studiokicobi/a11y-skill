# 0005: Unified Audit And CI Command Surface

## Status

Accepted

## Context

By the end of M7, the skill has a solid internal architecture, but the public operator workflow is still fragmented across multiple scripts. A capable user can chain the pieces together, but the default product experience is harder than it should be:

- too many entrypoints
- no single default artifact package
- reports describe findings well enough, but do not consistently tell the operator what to do next

The product goal is to make the tool feel like one coherent audit product rather than a toolkit of loosely related scripts.

## Decision

- Treat `scripts/cli.py` as the public command surface.
- Expose two public workflows only:
  - `audit`
  - `ci`
- Keep scanner and rendering scripts available as internal building blocks for fixtures, debugging, and advanced usage.
- Standardize default run output under one artifact directory per run, rooted under `.artifacts/a11y/<run-id>/`.
- Make the full markdown report start with:
  - one-line outcome summary
  - snapshot
  - artifact index
  - explicit next steps
- Require PR summaries to explain blocker scope and note when changed-files mode excluded findings because mapping confidence was too low.

## Consequences

- Public docs, agent instructions, and future implementation work should orient around `audit` and `ci`, not around the individual internal scripts.
- Internal script contracts still matter for fixtures and development, but they are no longer the default user-facing workflow.
- Artifact paths become more predictable and easier to hand off between local audit mode, CI mode, and human review.
- The next implementation phase should focus on orchestration, report packaging, and operator handoff before adding new scanner capabilities.
