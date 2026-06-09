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
| `templates.ts` | `/api/templates` | 6 endpoints | CRUD, apply to project |
| `settings.ts` | `/api/settings` | 4 endpoints | Provider key management |
| `presence.ts` | `/api/presence` | 2 endpoints | Real-time cursor presence |
| `progress.ts` | `/api/progress` | 1 endpoint | SSE progress stream |

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
├── status (uploading | analyzing | rendering | complete | failed)
├── styleTier (cuts_only | color_grade | with_text | with_effects | full_remix)
├── mode (auto | assisted)
├── referenceAssetId → assets.id (nullable)
├── songAssetId → assets.id (nullable)
├── clipAssetIds (JSONB array of asset IDs)
├── cutList (JSONB — full cutlist structure)
├── renderAssetId → assets.id (nullable)
├── createdAt
└── updatedAt

assets
├── id (UUID PK)
├── projectId → projects.id
├── type (reference | song | clip | render | preview)
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

| Worker | Primary Tasks | Key Libraries |
|---|---|---|
| **Ingest Worker** | Probe media metadata, detect beats, detect shot boundaries | PyAV, librosa, allin1, PySceneDetect, TransNet V2 |
| **Style Worker** | Extract LUT, classify transitions, detect text, analyze camera motion | PIL, scikit-learn, OpenCV |
| **Reason Worker** | Generate cutlist, rank clips per slot | Claude/OpenAI APIs, programmatic fallback |
| **Render Worker** | Compile final video with effects, transitions, overlays | FFmpeg, PyAV |
| **Upscale Worker** | Optional post-render upscaling | Real-ESRGAN, Topaz (placeholder) |

### Data Flow Between Workers

```
Reference Video + Song + Clips
    ↓
┌─────────────────┐
│  Ingest Worker  │
│  - probe ref    │
│  - detect beats │
│  - detect shots │
└────────┬────────┘
         ↓
┌─────────────────┐
│  Style Worker   │
│  - extract LUT  │
│  - transitions  │
│  - text overlays│
│  - camera motion│
└────────┬────────┘
         ↓
┌─────────────────┐
│  Reason Worker  │
│  - generate     │
│    cutlist      │
│  - rank clips   │
└────────┬────────┘
         ↓
[User review / prompt edit]
         ↓
┌─────────────────┐
│  Render Worker  │
│  - compile      │
│  - effects      │
│  - transitions  │
│  - audio mix    │
└────────┬────────┘
         ↓
    Final MP4
```

### Shared Python Library

All workers depend on `shared-py` which provides:
- **Pydantic models** (`models.py`) — Type-safe data structures with camelCase alias generation
- **AI provider abstraction** (`ai_providers/`) — Unified interface for Claude, OpenAI, Gemini, Groq, Kimi, Qwen, OpenRouter, plus programmatic fallback
- **Structured logging** (`logging_config.py`) — JSON-structured logs with correlation IDs

---

## Render Workflow (Temporal)

The `VideoRenderWorkflow` is a 10-step Temporal workflow that orchestrates the entire render pipeline:

### Workflow Steps

```
1. PROBE_INPUTS
   └─► Probe reference video, song, and all clips
   └─► Extract metadata: duration, resolution, codec, fps

2. DETECT_BEATS
   └─► Analyze song for beats, downbeats, and musical sections
   └─► Output: BeatGrid with timestamps and confidence

3. DETECT_SHOTS
   └─► Analyze reference video for shot boundaries
   └─► Output: ShotBoundary array with transition types

4. ANALYZE_REFERENCE_STYLE
   └─► Extract LUT (color grading)
   └─► Classify transitions
   └─► Detect text overlays
   └─► Analyze camera motion
   └─► Output: StyleAnalysis

5. EMBED_USER_CLIPS
   └─► Generate embeddings for user clips
   └─► Compute shot type, aesthetic, motion features

6. GENERATE_CUTLIST
   └─► AI-generated or programmatic cutlist
   └─► Maps shots to time slots in the song
   └─► Output: CutList with globals + slots

7. RANK_CLIPS_PER_SLOT
   └─► For each slot, rank user clips by relevance
   └─► Weighted scoring: semantic, shot type, aesthetic, motion, duration
   └─► Select top-1 clip per slot
   └─► Output: CutList with assigned clip IDs + confidence score

   [ASSISTED MODE: Workflow pauses here for user approval]
   
   User can:
   - Approve cutlist → workflow continues
   - Edit cutlist manually → send signal to workflow
   - Prompt-edit → API calls AI service, updates cutlist

8. RENDER_720P
   └─► Compile final video with FFmpeg
   └─► Apply effects, transitions, overlays, LUT
   └─► Mix audio tracks
   └─► Output: 720p MP4 + 360p preview

9. UPLOAD_TO_R2
   └─► Upload rendered video to object storage
   └─► Update render record with outputAssetId

10. NOTIFY_USER
    └─► Send completion notification
    └─► Update project status
```

### Temporal Configuration

- **Task Queue**: `video-render-queue`
- **Namespace**: `default`
- **Retry Policy**: Exponential backoff, max 3 attempts per activity
- **Signal**: `cutlistApproved` — resumes workflow after user review in assisted mode
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
API probes file with PyAV (via ingest worker or direct)
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
API creates render record (status: queued)
    ↓
API starts Temporal workflow
    ↓
API enqueues job to Redis queue
    ↓
Response: { job: { id, status, stage } }
    ↓
Frontend opens SSE to /api/progress/:jobId/events
    ↓
Temporal worker picks up workflow
    ↓
[Pipeline executes — see Temporal Workflow section]
    ↓
Each stage publishes progress to Redis pub/sub
    ↓
SSE endpoint broadcasts progress to frontend
    ↓
Workflow completes
    ↓
Worker POSTs to /api/renders/:jobId/complete
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
