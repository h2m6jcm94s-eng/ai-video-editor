# Architecture Documentation

> Comprehensive guide to the AI Video Editor system architecture, data flows, and design decisions.

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [System Architecture Diagram](#system-architecture-diagram)
- [Frontend Architecture](#frontend-architecture)
- [Backend Architecture](#backend-architecture)
- [Database Design](#database-design)
- [Worker Pipeline Architecture](#worker-pipeline-architecture)
- [Render Workflow (Temporal)](#render-workflow-temporal)
- [Authentication Flow](#authentication-flow)
- [Upload Flow](#upload-flow)
- [Render Flow](#render-flow)
- [AI Provider Chain](#ai-provider-chain)
- [Caching Strategy](#caching-strategy)
- [Real-Time Presence](#real-time-presence)
- [Error Handling Strategy](#error-handling-strategy)
- [Technology Decisions](#technology-decisions)

---

## High-Level Overview

The AI Video Editor is a full-stack application that automates video editing through AI analysis of reference videos, user clips, and music. The system consists of:

1. **Web Frontend** — Next.js 15 application with a video editor UI
2. **API Backend** — Fastify 4 server handling HTTP requests, auth, and orchestration
3. **Python Workers** — Specialized workers for video analysis, style extraction, and rendering
4. **Temporal** — Durable workflow orchestration for the render pipeline
5. **PostgreSQL** — Primary database for projects, assets, renders, users, templates
6. **Redis** — Caching, job queue, and real-time progress pub/sub
7. **R2/MinIO** — Object storage for video assets
8. **Internal API** — Worker-facing routes under `/api/internal` protected by `x-internal-token`

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT BROWSER                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Next.js   │  │   Clerk     │  │  Upload     │  │   SSE Progress      │ │
│  │   App       │  │   Auth      │  │  to R2      │  │   Subscription      │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                │                    │            │
└─────────┼────────────────┼────────────────┼────────────────────┼────────────┘
          │                │                │                    │
          ▼                ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY                                     │
│                         (Fastify 4 — Node.js)                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Routes    │  │   Auth      │  │  Validation │  │   Rate Limiting     │ │
│  │   (REST)    │  │ Middleware  │  │  (Zod)      │  │   (@fastify/rate)   │ │
│  └──────┬──────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│         │                                                                    │
│  ┌──────┴─────────────────────────────────────────────────────────────────┐  │
│  │                         SERVICES LAYER                                 │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │  │
│  │  │  AI      │ │ Temporal │ │  Queue   │ │ Storage  │ │   Cache      │ │  │
│  │  │ Service  │ │ Client   │ │ (Redis)  │ │  (R2)    │ │ (Redis)      │ │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
          │                │                │                    │
          ▼                ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  PostgreSQL │  │    Redis    │  │  R2/MinIO   │  │   Temporal Server   │ │
│  │  (Drizzle)  │  │  (ioredis)  │  │   (S3 API)  │  │   (Workflows)       │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
          │                                      │
          ▼                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PYTHON WORKERS                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐ │
│  │ Ingest       │ │ Style        │ │ Reason       │ │ Render              │ │
│  │ Worker       │ │ Worker       │ │ Worker       │ │ Worker              │ │
│  │ (probe, beat │ │ (LUT, trans- │ │ (cutlist,    │ │ (FFmpeg compile)    │ │
│  │  detect, shot│ │ ition, text, │ │  clip rank)  │ │                     │ │
│  │  detect)     │ │  camera)     │ │              │ │                     │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Frontend Architecture

### Technology Stack

- **Framework**: Next.js 15 with App Router
- **Runtime**: React 19 with Server Components by default
- **Styling**: Tailwind CSS + shadcn/ui component library (70+ components)
- **Auth**: Clerk (JWT-based, session management)
- **State**: Vanilla React (`useState`, `useReducer`) — no external state library
- **Forms**: react-hook-form + zodResolver using shared Zod schemas
- **API Client**: Custom abstraction (`apiServer` for RSC, `useApi()` for client)
- **Toasts**: Sonner
- **Icons**: Lucide React

### App Router Structure

```
app/
├── (auth)/           # Clerk auth pages
│   ├── sign-in/
│   └── sign-up/
├── dashboard/        # Project grid (RSC)
├── editor/
│   ├── new/          # Project creation form
│   └── [projectId]/  # Main editor (RSC shell + client editor)
├── settings/
│   └── keys/         # Provider API key manager
├── layout.tsx        # Root layout (ClerkProvider + ThemeProvider)
└── page.tsx          # Redirects to /dashboard
```

### Dashboard UI

The dashboard is built as a set of glassmorphic components in `apps/web/src/components/dashboard/`:

- `DashboardHeader` — top navigation with the project-create CTA
- `HeroSection` — value prop and project-count messaging
- `StatsSection` — four animated glass stat cards powered by `useCountUp` (`apps/web/src/hooks/useCountUp.ts`)
- `ProjectList` / `ProjectCard` — project grid with status badges and hover effects
- `CreateProjectDialog` — modal for naming a project and choosing a style tier / edit mode
- `AmbientBackground` — animated gradient orbs behind the glass panels

The glass look comes from Tailwind utilities defined in `apps/web/src/app/globals.css` (`.glass`, `.glass-card`, `.text-glass`, `.glow-hover`).

### Key Design Patterns

**1. Server/Client Boundary**
- Data fetching happens in Server Components via `apiServer`
- Interactive UI (editor, timeline, forms) lives in Client Components
- Clerk auth state is available on both sides

**2. Editor State Architecture**
The editor uses a complex reducer pattern in `useEditor.ts`:

```
EditorState
├── cutList
│   ├── globals (duration, tempo, resolution)
│   ├── slots[] (clip segments with timing)
│   ├── overlays[] (text, shapes, effects)
│   └── audioTracks[]
├── selection (selected slot/overlay)
├── zoom (timeline zoom level)
├── playback (play/pause, currentTime)
└── undoStack / redoStack
```

**3. File Upload Flow**
```
User selects file
    ↓
Frontend validates MIME type (video/*, audio/*)
    ↓
Request presigned URL from API
    ↓
PUT file directly to R2/MinIO (bypasses API for bandwidth)
    ↓
Notify API upload is complete
    ↓
API probes asset metadata (duration, dimensions, fps)
    ↓
Asset appears in media panel
```

**4. Real-Time Progress**
- Frontend opens SSE connection to `/api/progress/:jobId/events`
- Redis pub/sub broadcasts progress updates from workers
- Frontend displays progress bar with stage names
- Auto-reconnect with exponential backoff (max 5 retries)

---

## Backend Architecture

### Technology Stack

- **Runtime**: Node.js 20 (LTS)
- **Framework**: Fastify 4 (high-performance, plugin-based)
- **ORM**: Drizzle ORM with PostgreSQL
- **Validation**: Zod (shared with frontend via `@ai-video-editor/shared-types`)
- **Auth**: Clerk Fastify SDK + local user sync middleware
- **Queue**: Redis (sorted sets for priority, pub/sub for progress)
- **Cache**: Redis (30s TTL for list endpoints)
- **Storage**: Cloudflare R2 / MinIO (S3-compatible)
- **Workflows**: Temporal (durable execution)
- **Logging**: Pino (Fastify's built-in logger)

### Route Organization

All routes are registered in `app.ts` under the `/api` prefix. Auth middleware (`requireAuth`) is applied globally to all routes except health checks.

| Route Module | Prefix | Endpoints | Key Features |
|---|---|---|---|
| `health.ts` | `/api/health` | `GET /`, `GET /db` | Public health probes |
| `projects.ts` | `/api/projects` | 8 endpoints | CRUD, cutlist, transcribe, AI prompt edit |
| `uploads.ts` | `/api/uploads` | 4 endpoints | Presigned URLs, completion, asset probe |
| `renders.ts` | `/api/renders` | 4 endpoints | Start render, get/list, completion webhook |
| `internal.ts` | `/api/internal` | 5 endpoints | Worker-facing routes (`x-internal-token`) |
| `templates.ts` | `/api/templates` | 6 endpoints | CRUD, apply to project |
| `settings.ts` | `/api/settings` | 4 endpoints | Provider key management |
| `presence.ts` | `/api/presence` | 2 endpoints | Real-time cursor presence |
| `progress.ts` | `/api/progress` | 1 endpoint | SSE progress stream |
| `segments.ts` | `/api/segments` | 2 endpoints | Start / query segmentation workflow |

### Middleware Pipeline

```
Request → CORS → Rate Limit → Request ID → Auth (skip for /health)
    ↓
Route Handler → Validation (Zod preHandler)
    ↓
Service Layer → DB / Redis / Temporal / R2
    ↓
Response
```

### Error Handling

All errors are normalized through `sendError()` to a consistent JSON shape:

```json
{
  "error": "Human-readable message",
  "code": "MACHINE_READABLE_CODE",
  "details": {} // Optional additional context
}
```

HTTP status codes:
- `400` — Bad Request (validation, missing fields)
- `401` — Unauthorized (Clerk auth failure)
- `403` — Forbidden (resource ownership mismatch)
- `404` — Not Found
- `409` — Conflict (duplicate in-progress render)
- `422` — Unprocessable Entity (Zod validation failure)
- `429` — Too Many Requests (rate limit exceeded)
- `500` — Internal Server Error

### Rate Limiting

Configured per-endpoint via Fastify route config:

| Endpoint | Max Requests | Window |
|---|---|---|
| `POST /api/renders` | 3 | 1 minute |
| `POST /api/projects/:id/transcribe` | 5 | 1 minute |
| `POST /api/projects/:id/prompt` | 10 | 1 minute |
| Default | 60 | 1 minute |

---

## Database Design

### Schema Overview

```
users
├── id (UUID PK)
├── clerkId (string, unique)
├── email
├── name
├── createdAt
└── updatedAt

projects
├── id (UUID PK)
├── userId → users.id
├── name
├── status (uploading | processing | complete | failed)
├── styleTier (cuts_only | color_grade | with_text | with_effects | full_remix)
├── mode (auto | assisted)
├── referenceAssetId → assets.id (nullable)
├── songAssetId → assets.id (nullable)
├── clipAssetIds (JSONB array of asset IDs)
├── cutList (JSONB — full cutlist structure)
├── styleAnalysis (JSONB — LUT/motion/transition/text/genome results)
├── renderAssetId → assets.id (nullable)
├── createdAt
└── updatedAt

assets
├── id (UUID PK)
├── projectId → projects.id
├── type (reference_video | song | clip | render | preview | subtitle | lut | sfx | mask | style_genome)
├── filename
├── mimeType
├── sizeBytes
├── durationSec
├── width
├── height
├── fps
├── storageKey (R2 object key)
├── storageUrl (presigned URL, temporary)
├── metadata (JSONB — probe data)
├── createdAt
└── updatedAt

renders
├── id (UUID PK)
├── projectId → projects.id
├── status (queued | running | complete | failed)
├── stage (queued | probing | beat_detect | shot_detect | style_analysis | cutlist_gen | clip_rank | rendering | uploading | complete)
├── progress (0-100 integer)
├── workflowId (Temporal workflow ID)
├── outputAssetId → assets.id (nullable)
├── previewAssetId → assets.id (nullable)
├── errorMessage (nullable)
├── options (JSONB — render options such as export preset and duration cap)
├── startedAt
├── completedAt
├── createdAt
└── updatedAt

templates
├── id (UUID PK)
├── userId → users.id
├── name
├── description
├── cutList (JSONB)
├── tags (text array)
├── isPublic (boolean)
├── usageCount (integer)
├── createdAt
└── updatedAt

providerKeys
├── userId → users.id (part of composite PK)
├── provider (anthropic | openai | gemini | groq)
├── encryptedKey (base64 XOR-encrypted)
└── createdAt
```

### Indexing Strategy

All foreign keys have B-tree indexes. Additional indexes:
- `projects_user_idx` — For listing user's projects
- `assets_project_idx` — For loading project assets
- `renders_project_idx` — For loading project renders
- `templates_user_idx` — For listing user's templates

### JSONB Conventions

- `cutList` stores the full editing timeline (camelCase keys)
- `clipAssetIds` stores ordered array of clip asset UUIDs
- `metadata` stores probe-derived data (codec info, color space, etc.)
- All JSONB fields use camelCase for consistency across frontend/backend/Python

---

## Worker Pipeline Architecture

### Worker Responsibilities

| Worker | Type | Primary Tasks | Key Libraries |
|---|---|---|---|
| **Ingest Worker** | Temporal | Probe uploaded media metadata; detect beats; cache face detections | PyAV, librosa, temporalio |
| **Style Worker** | Temporal | Extract LUT, classify transitions, detect text, analyze camera motion, extract 50-feature Style Genome | PIL, scikit-learn, OpenCV, temporalio |
| **Reason Worker** | Temporal / On-demand | Generate cutlist, rank clips per slot, momentum/anticipation scoring, lyric overlays, audio mix | Claude/OpenAI APIs, programmatic fallback |
| **Render Worker** | Temporal | Compile final video with FFmpeg; identity-aware masks; NVENC/CUDA acceleration | FFmpeg, PyAV, temporalio |
| **Upscale Worker** | On-demand | Optional post-render upscaling | Real-ESRGAN, Topaz (placeholder) |
| **Segment Worker** | Temporal | Subject segmentation / mask generation; protagonist identity masks | SAM3, OpenCV, PyAV |

### Temporal Task Queues

| Queue | Worker | Workflow | Purpose |
|---|---|---|---|
| `ingest` | Ingest Worker | `ProbeAssetWorkflow` | One-shot probe of a single uploaded asset |
| `segment` | Segment Worker | `SegmentSubjectWorkflow` | Generate per-subject masks for a clip |
| `style` | Style Worker | `AnalyzeStyleWorkflow`, `AnalyzeGenomeWorkflow` | Reference style analysis and 50-feature Style Genome extraction |
| `video-render-queue` | Render Worker | `VideoRenderWorkflow` | End-to-end render: fetch, download, compile, upload, finalize |

### Data Flow (Current Temporal Pipeline)

```
User uploads asset
    ↓
API creates asset row + presigned URL
    ↓
Browser uploads to MinIO/R2
    ↓
Browser calls POST /uploads/:assetId/complete
    ↓
API starts ProbeAssetWorkflow on `ingest` queue
    ↓
Ingest Worker downloads asset → probes with PyAV
    ↓
PATCH /api/internal/assets/:assetId/probe (metadata)
    ↓
Asset appears as "ingested" in the editor
         ↓
[Optional] User requests subject segmentation on a clip
         ↓
API starts SegmentSubjectWorkflow on `segment` queue
         ↓
Segment Worker generates a mask video and PATCHes asset metadata
         ↓
A `mask` asset is linked to the source clip
         ↓
[Style Worker runs `AnalyzeStyleWorkflow` / `AnalyzeGenomeWorkflow` on reference video]
         ↓
[Ingest Worker caches face detections for selected clips on demand]
         ↓
[Reason Worker builds cut-list, ranks clips, and computes audio mix]
         ↓
User clicks Render
         ↓
API starts `VideoRenderWorkflow` on `video-render-queue`
         ↓
Render Worker:
  1. fetch_project   → GET /api/internal/projects/:id
  2. download_clips  → from MinIO/R2
  3. build_identity_masks → face clustering + SAM3 protagonist masks (optional)
  4. compile_video   → FFmpeg filter_complex (NVENC/CUDA when available)
  5. upload_render   → PUT to MinIO/R2
  6. finalize_render → PATCH /api/renders/:renderId/complete
         ↓
    Final MP4 + project/render status updated
```

All worker→API calls include `x-internal-token: <INTERNAL_WORKER_TOKEN>`.

### Shared Python Library

All workers depend on `shared-py` which provides:
- **Pydantic models** (`models.py`) — Type-safe data structures with camelCase alias generation
- **AI provider abstraction** (`ai_providers/`) — Unified interface for Claude, OpenAI, Gemini, Groq, Kimi, Qwen, OpenRouter, plus programmatic fallback
- **Structured logging** (`logging_config.py`) — JSON-structured logs with correlation IDs
- **Tuning constants** (`tuning.py`) — Centralized knobs for ranking, optical flow, identity clustering, compiler quality profiles, and NVENC defaults
- **Identity clustering** (`identity_cluster.py`) — DBSCAN-based face clustering and protagonist selection

---

### Face Detection & Identity Clustering

The ingest worker can sample frames from clips and extract face embeddings with [InsightFace](https://github.com/deepinsight/insightface). Detections are cached as `{clip}.faces.json` and clustered across the project with DBSCAN to discover recurring subjects (identities). The top identities by screen time become **protagonists**.

During render, the render worker:
1. Ensures face caches exist for every selected clip.
2. Clusters detections and picks the top-N protagonists.
3. For each selected clip containing a protagonist, requests a SAM3 subject mask.
4. Composites the mask as an alpha matte so text/effects can sit behind the subject.

If InsightFace, scikit-learn, or SAM3 is unavailable, the pipeline falls back gracefully: identity metadata is empty and no masks are applied.

---

### Style Genome Extraction

The Style Genome is a 50-feature numeric fingerprint extracted from a reference video. It is produced by the `AnalyzeGenomeWorkflow` on the `style` task queue and stored as a `style_genome` asset (or inside `project.styleAnalysis`).

The five feature families are:

| Family | What it captures |
|---|---|
| `cut_rhythm` | Cut density, duration stats, hard-cut vs gradual ratios, downbeat alignment |
| `motion` | Average/max motion energy, percentages of pan/tilt/zoom/handheld/gimbal |
| `dwell` | Face size ratios, subjects per shot, face screen time, protagonist presence |
| `audio_align` | Cuts aligned to beats/downbeats, music ducking frequency, dialogue stats |
| `composition` | Dominant shot size, close-up/medium/wide ratios, rule-of-thirds ratio |

The genome is computed cheaply from shot boundaries and the existing style analysis; missing inputs are derived automatically so callers can obtain a complete fingerprint from a video path alone.

---

### Hardware-Accelerated Rendering

The render compiler automatically uses NVIDIA NVENC when FFmpeg reports `h264_nvenc` support. Operators can disable it with `AVE_DISABLE_NVENC=1` or opt into CUDA hardware decode with `AVE_USE_HWACCEL=1`.

| Mode | Default | Override |
|---|---|---|
| NVENC encode | Auto-detected | `AVE_DISABLE_NVENC=1` forces libx264 |
| CUDA decode | Off | `AVE_USE_HWACCEL=1` enables `-hwaccel cuda` per segment; falls back to software decode on failure |

NVENC settings are controlled through `RenderConfig`:
- `use_nvenc` / `video_codec` — choose the encoder path
- `nvenc_preset` — `p1` (fastest) through `p7` (best quality)
- `nvenc_cq` — constant quality value (default `19`)

When NVENC is unavailable or explicitly disabled, the compiler falls back to `libx264` with the configured `video_preset` and `video_crf`.

---

### Render Quality Profiles & Clip Ordering

The offline render CLI and render compiler share a set of quality profiles defined in `shared_py.tuning.COMPILER.QUALITY_PROFILES`:

| Profile | libx264 preset | CRF | Use case |
|---|---|---|---|
| `preview` | `ultrafast` | 28 | Fast 360p previews |
| `draft` | `veryfast` | 23 | Iterative editing |
| `demo` | `medium` | 19 | Default social-media exports |
| `export` | `slow` | 17 | High-quality delivery |
| `archive` | `veryslow` | 15 | Archival masters |

Clip ranking supports a deterministic tie-break when the top candidates are statistically tied:

| Mode | Tie-break rule |
|---|---|
| `smart` | Keep score order (default) |
| `filename` | Alphabetical by filename |
| `upload` | Earliest upload time |
| `shuffle` | Deterministic per-slot shuffle |

The threshold for applying the tie-break is configured with `clip_order_smart_threshold` (default `0.15`).

---

## Render Workflow (Temporal)

The `VideoRenderWorkflow` is a 6-step Temporal workflow that renders a project cut-list to a final MP4.

### Workflow Steps

```
1. fetch_project
   └─► GET /api/internal/projects/:id
   └─► Returns cut-list, asset IDs, asset key map, active render job + options

2. download_clips
   └─► Download each clip from MinIO/R2 to a local temp path
   └─► Uses asset key map from fetch_project

3. build_identity_masks (optional)
   └─► Extract/cache faces for selected clips
   └─► Cluster identities, pick protagonists, request SAM3 masks

4. compile_video
   └─► Build FFmpeg filter_complex from cut-list
   └─► Apply masks, video effects, transitions, overlays, audio mix
   └─► Use NVENC/CUDA when available; otherwise libx264/software decode
   └─► Output: local MP4 file

5. upload_render
   └─► Upload rendered MP4 to MinIO/R2
   └─► Return storage key

6. finalize_render
   └─► PATCH /api/renders/:renderId/complete
   └─► API updates render status, project status, output asset
```

### Ingest Workflow

The `ProbeAssetWorkflow` is a single-activity workflow on the `ingest` queue:

```
ProbeAssetWorkflow(input: { asset_id, storage_key })
  └─► probe_asset
      └─► Download asset from MinIO/R2
      └─► Probe with PyAV
      └─► PATCH /api/internal/assets/:assetId/probe
```

### Temporal Configuration

- **Namespace**: `default`
- **Task queues**: `ingest` (probe), `video-render-queue` (render)
- **Retry Policy**: Exponential backoff, max 3 attempts per activity
- **Query**: `getProgress` — returns current stage and progress percentage

---

## Authentication Flow

```
┌─────────┐         ┌──────────┐         ┌─────────────┐         ┌─────────┐
│  User   │         │  Clerk   │         │    API      │         │   DB    │
└────┬────┘         └────┬─────┘         └──────┬──────┘         └───┬─────┘
     │                   │                      │                    │
     │  Sign in          │                      │                    │
     │──────────────────►│                      │                    │
     │                   │                      │                    │
     │  JWT Token        │                      │                    │
     │◄──────────────────│                      │                    │
     │                   │                      │                    │
     │  Request + Auth   │                      │                    │
     │─────────────────────────────────────────►│                    │
     │                   │                      │                    │
     │                   │                      │  Validate JWT      │
     │                   │◄─────────────────────│                    │
     │                   │                      │                    │
     │                   │  User info           │                    │
     │                   │─────────────────────►│                    │
     │                   │                      │                    │
     │                   │                      │  upsertUser()      │
     │                   │                      │───────────────────►│
     │                   │                      │                    │
     │                   │                      │  Local UUID        │
     │                   │                      │◄───────────────────│
     │                   │                      │                    │
     │                   │                      │  Set request.userId│
     │                   │                      │                    │
     │  Response         │                      │                    │
     │◄─────────────────────────────────────────│                    │
```

### Auth Middleware Details

1. Clerk SDK validates the JWT from the `Authorization` header
2. If valid, extracts Clerk user ID and fetches user profile (email, name)
3. Calls `upsertUser(clerkId, email, name)` to sync to local Postgres
4. Attaches `request.userId` (local UUID) for all downstream handlers
5. If Clerk validation fails, returns 401

### Fallback Behavior

If Clerk's `getUser()` fails (network error), the middleware falls back to placeholder email/name derived from the Clerk ID to prevent total auth failure.

---

## Upload Flow

```
User selects file in browser
    ↓
Frontend validates MIME type against allowlist
    ↓
POST /api/uploads/presigned
    Body: { filename, mimeType, sizeBytes }
    ↓
API validates auth, generates UUID for asset
    ↓
API creates presigned PUT URL from R2/MinIO
    ↓
Response: { assetId, url, fields }
    ↓
Browser PUTs file directly to R2 (bypasses API)
    ↓
On success, browser notifies API:
    POST /api/uploads/:assetId/complete
    ↓
API starts `ProbeAssetWorkflow` on the `ingest` task queue
    ↓
Ingest Worker downloads the file, probes with PyAV
    ↓
PATCH /api/internal/assets/:assetId/probe
    ↓
API stores metadata: duration, width, height, fps
    ↓
Asset ready for use in editor
```

### MIME Type Allowlist

| Type | Extensions | Max Size |
|---|---|---|
| Video | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` | 2 GB |
| Audio | `.mp3`, `.wav`, `.aac`, `.m4a`, `.flac` | 500 MB |

---

## Render Flow

```
User clicks "Render" in editor
    ↓
POST /api/renders
    Body: { projectId, options }
    ↓
API validates:
  - Project exists and user owns it
  - Required assets present (reference + song)
  - No render already in progress
    ↓
API collects any `mask` assets and builds a `maskSourceMap` from clip → mask
    ↓
API validates and stores render `options` (e.g. `exportPreset`, `durationSec`)
    ↓
API creates render record (status: queued)
    ↓
API starts `VideoRenderWorkflow` on `video-render-queue`
    Body includes the mask map and render options so the compiler can apply segmentation and pick dimensions/duration
    ↓
Response: { job: { id, status, stage } }
    ↓
Frontend opens SSE to /api/progress/:jobId/events
    ↓
Render Worker picks up workflow
    ↓
[Pipeline executes — see Render Workflow section]
    ↓
Each stage publishes progress to Redis pub/sub
    ↓
SSE endpoint broadcasts progress to frontend
    ↓
Workflow completes
    ↓
Worker PATCHes /api/renders/:jobId/complete
    ↓
API updates render status and project status
    ↓
User downloads final video
```

---

## AI Provider Chain

Both the Node.js API and Python workers implement a fallback chain for AI providers.

### Provider Priority

```
Primary Provider (env: AI_PROVIDER)
    ↓ (if fails with non-auth error)
Fallback Provider
    ↓ (if both fail)
Programmatic Fallback (reason-worker only)
    ↓ (if all fail)
Error returned to user
```

### Supported Providers

| Provider | Models Used | Use Case |
|---|---|---|
| **Claude (Anthropic)** | Claude 3.5 Sonnet | Prompt editing, cutlist generation |
| **OpenAI** | GPT-4o, Whisper | Prompt editing, transcription |
| **Gemini (Google)** | Gemini Pro | Fallback for cutlist generation |
| **Groq** | Llama 3, Mixtral | Fast fallback |
| **Kimi** | Kimi k1.5 | Chinese-language optimization |
| **Qwen** | Qwen 2.5 | Multilingual fallback |
| **OpenRouter** | Various | Unified API access |

### Provider Key Management

- Keys are stored per-user in the `provider_keys` table
- Encrypted at rest with XOR-based encryption (demo — replace with AES-256-GCM in production)
- API falls back to environment variables for admin/global keys
- UI shows "Connect [Provider]" CTA when a required key is missing

### Prompt Edit Flow

```
User enters natural language prompt
    ↓
System builds prompt context:
  - User request
  - Current cutlist (JSON)
  - Beat grid (if available)
  - Available assets list
    ↓
AI returns JSON Patch diff + explanation
    ↓
API applies JSON Patch to current cutlist
    ↓
Updated cutlist saved to database
    ↓
Response: { project, diff, explanation }
```

---

## Caching Strategy

### What Gets Cached

| Resource | Cache Key Pattern | TTL | Invalidation |
|---|---|---|---|
| User's projects list | `projects:list:{userId}` | 30s | On create/update/delete |
| User's templates list | `templates:list:{userId}` | 30s | On create/update/delete |

### What Does NOT Get Cached

- Individual project details (frequently mutated during editing)
- Render job status (must be real-time)
- Asset metadata (static after probe, but low query volume)
- User profile (Clerk handles this)

### Cache Implementation

```typescript
// Read-through cache pattern
const cached = await cacheGet(key);
if (cached) return cached;

const data = await db.query...;
await cacheSet(key, data, 30); // 30 second TTL
return data;
```

### Invalidation

All mutations (`POST`, `PATCH`, `DELETE`) call `cacheDel()` on the relevant list cache key before returning. This ensures list views are immediately consistent.

---

## Real-Time Presence

The presence system enables real-time cursor sharing in the editor (for collaborative editing).

### Implementation

- **Storage**: In-memory `Map<string, Map<string, CursorData>>` (no persistence needed)
- **TTL**: 15 seconds — stale cursors are cleaned up on read
- **Color assignment**: Deterministic hash of user ID mapped to a palette of 8 colors

### Data Flow

```
User moves cursor
    ↓
POST /api/presence/:projectId
    Body: { x, y, name }
    ↓
Server stores in presenceStore[projectId][userId]
    ↓
Other users poll GET /api/presence/:projectId
    ↓
Server filters out requesting user, returns active cursors
    ↓
Frontend renders cursors on editor canvas
```

### Limitations

- No WebSocket — polling-based (simpler, sufficient for cursor presence)
- No persistence — cursors disappear on server restart
- No room management — anyone with project access can see cursors

---

## Error Handling Strategy

### Error Taxonomy

| Category | HTTP Status | Example Codes |
|---|---|---|
| Auth | 401 | `UNAUTHORIZED`, `SESSION_EXPIRED` |
| Authorization | 403 | `FORBIDDEN`, `PLAN_LIMIT` |
| Validation | 400, 422 | `VALIDATION_ERROR`, `MISSING_FIELD` |
| Resource | 404 | `NOT_FOUND` |
| Conflict | 409 | `CONFLICT`, `ALREADY_EXISTS` |
| Provider | 400, 429, 500 | `PROVIDER_KEY_MISSING`, `PROVIDER_RATE_LIMITED`, `PROVIDER_INVALID_RESPONSE` |
| AI/Pipeline | 500 | `AI_ERROR`, `TEMPORAL_ERROR` |
| Infrastructure | 500 | `INTERNAL_ERROR`, `STORAGE_ERROR` |

### Frontend Error Handling

1. API client intercepts errors and converts to `ApiError` objects
2. `APIError.userMessage` provides human-friendly text for toasts
3. Auth errors redirect to sign-in page
4. Provider errors show "Connect Provider" CTA
5. Validation errors highlight form fields

### Backend Error Handling

1. Route handlers catch expected errors and return structured responses
2. Fastify's `setErrorHandler` catches uncaught errors
3. All errors are logged with full context (URL, user, stack trace)
4. Client errors (4xx) include original message; server errors (5xx) are sanitized

---

## Technology Decisions

### Why Fastify over Express?

Fastify provides better performance out of the box, built-in JSON schema validation, and a cleaner plugin architecture. The difference is particularly noticeable for high-throughput endpoints like presigned URL generation and health checks.

### Why Temporal over simple queues?

Temporal provides durable execution — if a worker crashes mid-render, the workflow resumes from the last completed activity. This is critical for long-running render jobs (10+ minutes). It also handles signals (user approval) and queries (progress checks) natively.

### Why pnpm workspaces?

pnpm's content-addressable store deduplicates dependencies across packages, reducing disk usage. Its workspace protocol (`workspace:*`) ensures local packages are always linked correctly. The lockfile is deterministic and fast.

### Why no state management library?

The editor's state is complex but localized. `useReducer` provides sufficient structure without the overhead of Redux/Zustand. Server state is fetched fresh via Server Components. The only shared client state is auth (handled by Clerk).

### Why XOR encryption for provider keys?

The current XOR-based encryption is explicitly marked as a demo implementation. It was chosen for simplicity during development. Production deployments should replace it with AES-256-GCM with a Key Encryption Key (KEK) managed by a secrets manager (HashiCorp Vault, AWS KMS, etc.).

### Why R2/MinIO over S3?

Cloudflare R2 has no egress fees, making it cost-effective for video delivery. MinIO provides a self-hosted S3-compatible option for local development without cloud dependencies. Both use the same S3 API, so switching between them is a configuration change.

---

## Related Documentation

- [`API.md`](./API.md) — Complete API endpoint reference
- [`DEVELOPMENT.md`](./DEVELOPMENT.md) — Local development setup guide
- [`TESTING.md`](./TESTING.md) — Testing strategy and patterns
- [`DEPLOYMENT.md`](./DEPLOYMENT.md) — Production deployment guide
