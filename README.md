# AI Video Editor — Reference Style Matching

[![License: ELv2](https://img.shields.io/badge/License-Elastic_v2-blue.svg)](https://www.elastic.co/licensing/elastic-license)

> **Claude Code for video editing.** AI generates a working baseline from a reference video + song + clips + style tier. Newbies hit render and ship. Power users refine via prompts and manual controls.

## What it does

1. Upload a **reference video** — the style you want to match (cuts, color, text, transitions).
2. Upload your **clips** — the footage to edit.
3. Upload a **song** — the music to sync to.
4. Pick a **style tier** from the 5-tier ladder.
5. Hit render, or prompt-edit the cut list until it's perfect.

## 5-Tier StyleTier Ladder

| Tier | What runs | When to use |
|------|-----------|-------------|
| `cuts_only` | Beat detect + shot detect → AI cut list | "Just sync my clips to the beat" |
| `color_grade` | + LUT extraction from reference | "Match the reference's color only" |
| `with_text` | + Text overlay extraction (PaddleOCR) | "Ad-style titles like the reference" |
| `with_effects` | + Transition classifier + camera motion + SFX | "Borrow the reference's edit feel" |
| `full_remix` | All above + manual effects, multi-song, prompt edits | "AI baseline, now I'm directing" |

## Quick start

```bash
pnpm install
pnpm dev
```

Then open `http://localhost:3000`, sign in with Clerk, and add your AI provider keys in **Settings → API Keys**. No `.env` required for AI providers in local dev.

## Architecture

```
repo/
├── apps/
│   ├── web/           # Next.js 15 + Tailwind + shadcn/ui
│   └── api/           # Fastify 4 + Temporal + Drizzle
├── packages/
│   ├── shared-types/  # Zod schemas, enums, errors, effects
│   └── eslint-config
├── services/          # Python workers (uv workspace)
│   ├── render-worker/
│   ├── ingest-worker/
│   ├── style-worker/
│   ├── reason-worker/
│   └── shared-py/
└── infra/             # Docker, Temporal, deploy configs
```

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, Tailwind CSS, shadcn/ui, Clerk |
| Backend | Fastify 4, Drizzle ORM, Postgres, Redis, MinIO |
| Orchestration | Temporal |
| AI | Claude 3.5 Sonnet, GPT-4o, Whisper |
| Render | FFmpeg, PyAV |
| Language | TypeScript 5.4, Python 3.11 |
| Package manager | pnpm 9.15 |

## In-app key entry

AI provider keys are stored per-user in the `provider_keys` table, encrypted at rest. The app falls back to env vars for admin/global keys. If a feature needs a missing key, the UI shows a "Connect [Provider]" CTA instead of crashing.

## Scripts

```bash
pnpm dev           # Start web + api + shared-types watch
pnpm typecheck     # Type-check all packages
pnpm --filter api test           # Run API tests
pnpm --filter api test:coverage  # Run API tests with coverage report
pnpm --filter web test           # Run frontend tests
```

## License

Elastic License 2.0. Commercial SaaS use requires written permission.
