# apps/api/AGENTS.md

## Route + middleware conventions

1. Every route file in `src/routes/*.ts` exports `async function xxxRoutes(app: FastifyInstance)`.
2. Every mutation endpoint uses `validateBody(schema)` from `src/middleware/validate.ts`.
3. Validation schemas are imported from `@ai-video-editor/shared-types`. No local Zod duplication.
4. Use `request.log.error({ err }, "message")` for errors; Fastify logger is enabled.
5. Return structured errors: `{ error: string, code: ApiErrorCode, details? }`.
6. Use `request.userId` (set by auth middleware) for ownership checks.
7. DB queries prefer `db.query.xxx.findFirst/findMany` for reads; `db.insert/update/delete` for writes.
