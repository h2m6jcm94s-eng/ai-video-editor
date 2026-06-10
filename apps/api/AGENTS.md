# apps/api/AGENTS.md

## Route + middleware conventions

1. Every route file in `src/routes/*.ts` exports `async function xxxRoutes(app: FastifyInstance)`.
2. Every mutation endpoint uses `validateBody(schema)` from `src/middleware/validate.ts`.
3. Validation schemas are imported from `@ai-video-editor/shared-types`. No local Zod duplication.
4. Use `request.log.error({ err }, "message")` for errors; Fastify logger is enabled.
5. Return structured errors: `{ error: string, code: ApiErrorCode, details? }`.
6. Use `request.userId` (set by auth middleware) for ownership checks.
7. DB queries prefer `db.query.xxx.findFirst/findMany` for reads; `db.insert/update/delete` for writes.

## Logging conventions

- **Development**: `pino-pretty` transport for human-readable logs.
- **Production**: `pino-loki` transport ships logs to Loki (`LOKI_URL` env, default `http://loki:3100`).
- Use `request.log[level]({ ...context }, "message")` everywhere. Never `console.log/warn/error` in route handlers.
- The only allowed `console.*` calls are in `index.ts` bootstrap (before Fastify starts) and `env.ts` (startup failure banner).

## Observability

- **Tracing**: `src/lib/tracing.ts` initializes OpenTelemetry NodeSDK. Auto-instrumentations cover HTTP, DB, Redis. OTLP HTTP exporter sends to `OTEL_EXPORTER_OTLP_ENDPOINT`.
- **Metrics**: Prometheus metrics in `src/lib/metrics.ts`. Exposed at `GET /api/metrics`.
- **Frontend logs**: `POST /api/log` ingests batched frontend events. Validates with Zod, writes to `request.log`.

## New routes checklist

- [ ] Import schema from `@ai-video-editor/shared-types`
- [ ] Use `validateBody(schema)` for mutations
- [ ] Add `request.log` calls for errors and slow paths
- [ ] Add tests in `src/test/`
- [ ] Add OpenAPI entry in `apps/api/openapi.yaml`
