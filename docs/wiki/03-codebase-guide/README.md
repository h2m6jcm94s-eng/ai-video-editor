# Codebase Guide

This section walks through every major area of the monorepo. Each page focuses on one layer and maps folders/files to their responsibilities.

| Page | Coverage |
|---|---|
| [`01-apps.md`](./01-apps.md) | `apps/api/` (Fastify backend), `apps/web/` (Next.js frontend), `apps/desktop/` (Tauri) |
| [`02-services.md`](./02-services.md) | Python workers: ingest, style, reason, render, segment, upscale, shared-py, orchestrator |
| [`03-packages-infra-scripts.md`](./03-packages-infra-scripts.md) | Shared types, ESLint config, Docker/Modal/observability infrastructure, scripts, root config, e2e and integration tests |

## How to use this guide

- Start with the service or app you are debugging.
- Follow the file references into the source.
- For algorithms and formulas, see [`../02-mathematical-foundations.md`](../02-mathematical-foundations.md).
- For product features and user flows, see [`../01-features-overview.md`](../01-features-overview.md).
