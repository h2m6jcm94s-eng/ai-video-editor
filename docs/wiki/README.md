# AI Video Editor — Complete Project Wiki

> One-stop reference for the AI Video Editor monorepo. This wiki explains the product features, the math behind the pipeline, how the code is organized, and what is coming next.

## Quick navigation

| File | What you'll find |
|---|---|
| [`01-features-overview.md`](./01-features-overview.md) | Product features, user flows, and what each pipeline stage does |
| [`02-mathematical-foundations.md`](./02-mathematical-foundations.md) | Algorithms, formulas, and scoring functions used by workers |
| [`03-codebase-guide/`](./03-codebase-guide/README.md) | Per-folder, per-file walkthrough of the monorepo |
| [`04-upcoming-features.md`](./04-upcoming-features.md) | Roadmap and deep-dive on the next two planned features |
| [`05-glossary.md`](./05-glossary.md) | Terms, acronyms, and external tools/libraries |

## How this wiki is maintained

- Code paths are given relative to the repo root, e.g. `services/render-worker/src/render_worker/compiler.py`.
- Line numbers refer to the version of `main` at the time of writing; use `git grep` or your IDE to follow them as the code evolves.
- The wiki is written for engineers who need to onboard, debug, or extend the pipeline.

## Related docs

- High-level user docs: [`docs/README.md`](../README.md) (if present), [`README.md`](../../README.md)
- Architecture: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
- API reference: [`docs/API.md`](../API.md) and [`apps/api/openapi.yaml`](../../apps/api/openapi.yaml)
- Development setup: [`docs/DEVELOPMENT.md`](../DEVELOPMENT.md)
- Deployment: [`docs/DEPLOYMENT.md`](../DEPLOYMENT.md)
- Testing: [`docs/TESTING.md`](../TESTING.md)
- Roadmap: [`ROADMAP.md`](../../ROADMAP.md)
- Handoff / session notes: [`HANDOFF.md`](../../HANDOFF.md)
