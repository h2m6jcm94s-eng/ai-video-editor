# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Production hardening: startup env validation, connection probes (DB, R2, Redis)
- Auth middleware with Clerk JWT validation on all API routes
- Rate limiting (`@fastify/rate-limit`) on API endpoints
- Zod request validation on all write routes
- API test suite with 26 vitest tests covering health, projects, uploads, renders, progress
- Python worker startup validation (`shared_py/startup.py`)
- AI provider init key validation (Claude, Gemini, Groq, OpenAI, OpenRouter, Qwen)
- FFmpeg error context wrappers in compiler.py and beat_detect.py
- Cross-platform font fallback in render compiler
- Next.js error boundaries (`error.tsx`, `global-error.tsx`)
- Typed API client with `APIError` class
- Redis SSE subscriber memory leak fix (shared map + refcount)
- Queue safe JSON parse + priority via zadd/zpopmin
- Temporal workflow idempotency with collision-free workflow IDs
- Project asset cleanup on delete (async R2 deletion)
- `workflowId` column on renders with cascade deletes
- CI/CD workflows for tests, typecheck, Docker builds, security audits

### Fixed

- FFmpeg filter injection (LUT path + overlay text escaping)
- Audio mapping in compiler.py
- Negative xfade offset handling
- Shot detection hardcoded 30fps → parameterized
- Optical flow drift in camera_motion.py (p0 reset)
- Zero-norm guard in clip_rank.py
- Cross-platform temp dir (`tempfile.gettempdir()`)
- `GEMINI_API_KEY` → `GOOGLE_API_KEY` consistency across codebase

## [0.1.0] - 2024-05-13

### Added

- Initial MVP release
- Fastify API with project/asset/render CRUD
- Next.js web frontend
- Python workers: ingest, style, reason, render
- Temporal workflow orchestration
- R2/S3-compatible storage integration
- PostgreSQL + Drizzle ORM
- Redis queue + SSE progress streaming
- Multi-provider AI support (Claude, Gemini, OpenAI, Groq, OpenRouter, Qwen, Kimi)
