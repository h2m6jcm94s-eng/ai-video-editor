# AGENTS.md — Orientation for AI Assistants

## What this repo is

An AI-powered video editor monorepo. The product vision: "Claude Code for video editing" — AI generates a working baseline from reference video + song + clips + style tier; power users refine via prompts and manual controls.

## Monorepo layout

```
apts/
  web/           Next.js 15 frontend (Clerk auth, Tailwind, shadcn/ui)
  api/           Fastify 4 backend (Temporal, Drizzle, Postgres, Redis)
packages/
  shared-types/  Source of truth for Zod schemas, enums, errors, effects
  eslint-config  Shared lint rules
services/        Python workers (render, ingest, style, reason) — uv workspace
infra/           Docker, Temporal, deployment configs
```

## Cross-boundary rules (non-negotiable)

1. **Single source of truth**: Any schema shared between frontend and backend lives in `packages/shared-types`. Never duplicate enums or validation logic.
2. **camelCase for CutList JSONB** everywhere (frontend types, backend responses, AI prompts, Python alias_generator). The DB stores snake_case legacy in some rows; new code uses camelCase.
3. **No silent `catch {}`**: Every catch must log + toast or re-throw. See `APIError.userMessage` pattern.
4. **Forms use react-hook-form + zodResolver + shared schemas**. No raw `useState` form state in new code.
5. **Forbidden additions**: Redux, Zustand, Jotai, Mobx, CSS Modules, styled-components, emotion. Use vanilla `useState`/`useReducer` and Tailwind only.
6. **Auth**: Server components use `apiServer`. Client components use `useApi()`. Never pass Clerk tokens manually.
7. **Effect catalog**: Every new effect needs shared schema → web preview → Python render impl → test.

## Where to find things

- Shared schemas: `packages/shared-types/src/{enums,schemas,errors,effects}.ts`
- API client: `apps/web/src/lib/api/{core,server,client,error}.ts`
- Backend routes: `apps/api/src/routes/*.ts`
- Backend validation: `apps/api/src/middleware/validate.ts`
- Editor state: `apps/web/src/hooks/useEditor.ts`
- Domain glossary: `CONTEXT.md` (create if missing)

## Workflow norms (issue-first, small PRs)

1. **Every change starts with an issue.** Open a GitHub issue describing the bug/feature/refactor before writing code.
2. **Branch naming**: `feat/<issue-number>-short-desc`, `fix/<issue-number>-short-desc`, `chore/<issue-number>-short-desc`.
3. **One concern per PR.** A PR should be reviewable in under 15 minutes. If it's longer, split it.
4. **PR description must reference the issue**: `Closes #<issue-number>`.
5. **No spam bots.** We intentionally do NOT use pr-agent, Danger, semantic-pr, or any workflow that posts PR comments or sends email spam. Auto-labels only (path-based + first-time contributor + keyword matching).
6. **Merge when CI is green.** Use squash merge. Keep commit messages descriptive.

## Before you make changes

1. Run `pnpm typecheck` after any TS change.
2. Run `pnpm test --filter=@ai-video-editor/api` after any backend change.
3. Update this file or the layer-specific `AGENTS.md` if you add a new convention.
4. Prefer minimal changes. The codebase is fragile; small PRs win.
