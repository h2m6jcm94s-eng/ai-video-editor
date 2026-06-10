# apps/web/AGENTS.md

## Editor conventions

1. `useEditor.ts` is the single state machine for the cut list. Add new actions there; don't create parallel state.
2. Every form must use `react-hook-form` + `zodResolver` + a shared schema from `packages/shared-types`.
3. Toasts go through `sonner`. Error messages come from `APIError.userMessage`.
4. Keyboard shortcuts are registered in `EditorLayout.tsx` `handleKeyDown`.
5. The Cmd+K command palette actions are defined in `EditorLayout.tsx` — register new features there.
6. Tailwind only. Dynamic state styles (overlay positions) use inline `style={{}}` with typed props.

## Error handling

1. **Never silently swallow errors.** Every `catch` must either:
   - Call `console.error(err)` (minimum)
   - Call `logger.error("msg", err)` (preferred — sends to GlitchTip)
   - Show a toast via `toast.error(...)`
   - Re-throw to an ErrorBoundary
2. **Error boundaries** (`error.tsx`, `global-error.tsx`) use `logger.error()` to report to GlitchTip.

## Logging

- `apps/web/src/lib/logger.ts` — batching frontend logger.
- Flushes to `POST /api/log` every 5 seconds or 10 events.
- `keepalive: true` ensures logs survive page close.
- Use `logger[level]("message", context?)` instead of `console.*` in production code.

## Error tracking

- Sentry/GlitchTip configs: `sentry.client.config.ts`, `sentry.edge.config.ts`, `sentry.server.config.ts`.
- DSN points at self-hosted GlitchTip (Sentry-compatible).
- Source maps uploaded automatically in CI.
