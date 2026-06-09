# apps/AGENTS.md

## Next.js + Fastify + Tauri conventions

### Apps in this layer
- `apps/web` — Next.js 15 frontend
- `apps/api` — Fastify 4 backend
- `apps/desktop` — Tauri (Rust) desktop wrapper

### Shared rules

1. All API routes are prefixed with `/api` in Fastify and mapped to `NEXT_PUBLIC_API_URL=http://localhost:4000/api` in web `.env.local`.
2. Frontend components that call the API must use:
   - `apiServer` in server components / route handlers
   - `useApi()` hook in client components
3. Environment variables must be validated via Zod (`apps/api/src/env.ts`, `apps/web/src/lib/env.ts` if created).
4. Error codes from `packages/shared-types/src/errors.ts` only. No ad-hoc strings.
5. **Frontend tests**: Use Vitest + React Testing Library. Place tests next to source (`*.test.{ts,tsx}`) or in `src/test/`. Import `@testing-library/jest-dom` matchers in `src/test/setup.ts`.
