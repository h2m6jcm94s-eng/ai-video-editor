# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Shared schemas package (`packages/shared-types`) with Zod schemas, enums, errors, and effects.
- In-app provider key management with encrypted storage and test-connection endpoint.
- Settings page with sidebar tabs (Account, API Keys, Appearance, Shortcuts, Advanced).
- Command palette (Cmd+K / Ctrl+K) for editor actions.
- Effect library shared types with 15 effects (zoom, focus pull, freeze frame, speed ramp, shake, glitch, vignette, film grain, color pop, text kinetic, lower third, callout arrow, SFX).
- Multi-audio track types (`AudioTrack[]`) in cut list.
- Render completion webhook (`POST /api/renders/:jobId/complete`).
- Contract tests for all shared schemas and upload validation.
- Structured logging with request IDs and Fastify logger.
- Layered AGENTS.md and CONTEXT.md documentation.

### Changed
- API client split into server (`apiServer`) and browser (`useApi`) surfaces with shared `createAPI` factory.
- All editor forms migrated to `react-hook-form` + shared Zod schemas.
- AI model fixes: Claude → `claude-3-5-sonnet-20241022`, OpenAI → `gpt-4o`.
- AI service reads per-user provider keys from DB, falls back to env.
- SSE progress reconnects with exponential backoff on disconnect.
- Upload uses PUT raw file with XMLHttpRequest progress and mime gate.

### Fixed
- Clerk auth now syncs users to local DB and sets `request.userId` to local UUID.
- 401 errors return proper `UNAUTHORIZED` code with user-facing toasts.
- Upload no longer sends POST to a PUT presigned URL.
- Render route returns 409 when a render is already in progress.

## [0.1.0] — 2025-06-01

### Added
- Initial monorepo setup with Next.js, Fastify, Temporal, Drizzle, MinIO.
- Project creation, asset upload, AI prompt editing, render pipeline.
- Basic editor with timeline, inspector, preview, and subtitles.
