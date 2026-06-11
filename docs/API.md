# API Reference

> Complete reference for all HTTP endpoints in the AI Video Editor API.
>
> **For the authoritative machine-readable spec, see [`apps/api/openapi.yaml`](../apps/api/openapi.yaml)** — import into Postman, Insomnia, or view with Swagger UI / Redoc.

**Base URL**: `https://api.example.com/api` (production) / `http://localhost:4000/api` (local)

**Authentication**: All endpoints require a Clerk JWT in the `Authorization` header or Clerk session cookie except health checks and metrics.

**Content-Type**: `application/json` unless otherwise specified.

**Error Format**:
```json
{
  "error": "Human-readable description",
  "code": "MACHINE_CODE",
  "details": {}
}
```

---

## Table of Contents

- [Health](#health)
- [Metrics](#metrics)
- [Projects](#projects)
- [Uploads](#uploads)
- [Renders](#renders)
- [Internal](#internal)
- [Templates](#templates)
- [Settings](#settings)
- [Presence](#presence)
- [Progress](#progress)
- [Log Ingestion](#log-ingestion)

---

## Health

### `GET /api/health`

Basic service health check.

**Auth**: None

**Response**:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

**Status Codes**:
- `200` — Service is healthy

---

### `GET /api/health/db`

Database connectivity check.

**Auth**: None

**Response**:
```json
{
  "status": "ok",
  "database": "connected",
  "latency_ms": 2
}
```

**Status Codes**:
- `200` — Database is reachable
- `503` — Database is unreachable

---

## Projects

### `GET /api/metrics`

Prometheus metrics exposition. Returns metrics in Prometheus text format.

**Auth**: Optional `Bearer <METRICS_AUTH_TOKEN>` when `METRICS_AUTH_TOKEN` is configured. Bypassed in test mode.

**Response**: `text/plain` with Prometheus exposition format.

**Status Codes**:
- `200` — Metrics returned
- `401` — Invalid or missing token

---

### `GET /projects`

List all projects for the authenticated user.

**Auth**: Required

**Query Parameters**: None

**Response**:
```json
{
  "projects": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Summer Vlog",
      "status": "complete",
      "styleTier": "full_remix",
      "mode": "auto",
      "referenceAssetId": "550e8400-e29b-41d4-a716-446655440001",
      "songAssetId": "550e8400-e29b-41d4-a716-446655440002",
      "clipAssetIds": ["550e8400-e29b-41d4-a716-446655440003"],
      "cutList": {
        "globals": {
          "totalDurationS": 120,
          "tempoBpm": 128,
          "resolution": "1920x1080"
        },
        "slots": [
          {
            "index": 0,
            "startS": 0,
            "durationS": 5.2,
            "assetId": "550e8400-e29b-41d4-a716-446655440003",
            "transitionIn": "hard_cut"
          }
        ],
        "overlays": [],
        "audioTracks": []
      },
      "renderAssetId": "550e8400-e29b-41d4-a716-446655440004",
      "createdAt": "2025-01-10T08:00:00Z",
      "updatedAt": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized

---

### `POST /projects`

Create a new project.

**Auth**: Required

**Request Body**:
```json
{
  "name": "My Project",
  "styleTier": "full_remix",
  "mode": "auto"
}
```

**Validation Rules**:
- `name`: Required, string, max 200 characters
- `styleTier`: Optional, enum `cuts_only | color_grade | with_text | with_effects | full_remix`, defaults to `full_remix`
- `mode`: Optional, enum `auto | assisted`, defaults to `auto`

**Response**:
```json
{
  "project": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My Project",
    "status": "uploading",
    "styleTier": "full_remix",
    "mode": "auto",
    "clipAssetIds": [],
    "createdAt": "2025-01-15T10:30:00Z",
    "updatedAt": "2025-01-15T10:30:00Z"
  }
}
```

**Status Codes**:
- `200` — Created successfully
- `400` — Invalid request body
- `401` — Unauthorized

---

### `GET /projects/:id`

Get a single project by ID.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Response**:
```json
{
  "project": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "My Project",
    "status": "uploading",
    "styleTier": "full_remix",
    "mode": "auto",
    "referenceAssetId": null,
    "songAssetId": null,
    "clipAssetIds": [],
    "cutList": null,
    "renderAssetId": null,
    "createdAt": "2025-01-15T10:30:00Z",
    "updatedAt": "2025-01-15T10:30:00Z"
  }
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized
- `403` — Forbidden (project belongs to another user)
- `404` — Project not found

---

### `PATCH /projects/:id`

Update project fields.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Request Body** (all fields optional):
```json
{
  "name": "Updated Name",
  "styleTier": "with_effects",
  "mode": "assisted"
}
```

**Validation Rules**:
- `name`: Optional, string, max 200 characters
- `styleTier`: Optional, enum
- `mode`: Optional, enum

**Response**:
```json
{
  "project": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Updated Name",
    "status": "uploading",
    "styleTier": "with_effects",
    "mode": "assisted",
    "updatedAt": "2025-01-15T11:00:00Z"
  }
}
```

**Status Codes**:
- `200` — Updated successfully
- `400` — Invalid request body
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Project not found

---

### `PATCH /projects/:id/cutlist`

Update the cutlist and trigger rendering (assisted mode).

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Request Body**:
```json
{
  "cutList": {
    "globals": {
      "totalDurationS": 120,
      "tempoBpm": 128
    },
    "slots": [
      {
        "index": 0,
        "startS": 0,
        "durationS": 5.2,
        "assetId": "550e8400-e29b-41d4-a716-446655440003",
        "transitionIn": "fade"
      }
    ]
  }
}
```

**Validation Rules**:
- `cutList`: Required, object

**Response**:
```json
{
  "project": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "rendering",
    "cutList": { /* ... */ },
    "updatedAt": "2025-01-15T11:00:00Z"
  }
}
```

**Status Codes**:
- `200` — Updated successfully
- `400` — Invalid request body
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Project not found

**Side Effects**:
- Sets project status to `rendering`
- If an active render workflow exists, sends `cutlistApproved` signal to Temporal

---

### `POST /projects/:id/transcribe`

Transcribe an audio asset to subtitles.

**Auth**: Required
**Rate Limit**: 5 requests per minute

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Request Body**:
```json
{
  "assetId": "550e8400-e29b-41d4-a716-446655440002"
}
```

**Validation Rules**:
- `assetId`: Required, string, must be a valid asset in the project

**Response**:
```json
{
  "subtitles": [
    {
      "id": "sub-0",
      "text": "Hello world",
      "startS": 0,
      "endS": 2.5
    },
    {
      "id": "sub-1",
      "text": "Welcome to the show",
      "startS": 3.0,
      "endS": 5.5
    }
  ]
}
```

**Status Codes**:
- `200` — Transcription successful
- `400` — Missing assetId or asset not found
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Project not found

**Notes**:
- Downloads asset from R2 to a temporary file
- Calls OpenAI Whisper API
- Cleans up temporary file after processing
- Requires `OPENAI_API_KEY` (env or user-configured)

---

### `POST /projects/:id/prompt`

Apply an AI-powered prompt edit to the cutlist.

**Auth**: Required
**Rate Limit**: 10 requests per minute

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Request Body**:
```json
{
  "prompt": "Make the first clip fade in slowly"
}
```

**Validation Rules**:
- `prompt`: Required, string, max 2000 characters

**Response**:
```json
{
  "project": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "cutList": { /* updated cutlist */ },
    "updatedAt": "2025-01-15T11:00:00Z"
  },
  "diff": [
    {
      "op": "replace",
      "path": "/slots/0/transitionIn",
      "value": "fade"
    }
  ],
  "explanation": "Changed the first slot's transition from hard_cut to fade for a smoother entry."
}
```

**Status Codes**:
- `200` — Edit applied successfully
- `400` — No cutlist to edit, or provider key missing
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Project not found
- `500` — AI service error

**Notes**:
- Requires the project to have a `cutList`
- Uses Claude 3.5 Sonnet by default (configurable via `AI_PROVIDER`)
- Falls back to OpenAI GPT-4o if primary provider fails
- Returns JSON Patch diff for transparency

---

### `DELETE /projects/:id`

Delete a project and all associated assets.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Response**:
```json
{
  "success": true
}
```

**Status Codes**:
- `200` — Deleted successfully
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Project not found

**Side Effects**:
- Deletes project record from database
- Asynchronously deletes all assets from R2 (fire-and-forget)
- Invalidates projects list cache

---

## Uploads

### `POST /uploads/presigned`

Generate a presigned upload URL for direct browser-to-R2 upload.

**Auth**: Required

**Request Body**:
```json
{
  "filename": "clip.mp4",
  "mimeType": "video/mp4",
  "sizeBytes": 52428800
}
```

**Validation Rules**:
- `filename`: Required, string
- `mimeType`: Required, must be in allowlist (video/* or audio/*)
- `sizeBytes`: Required, integer, must be positive

**Response**:
```json
{
  "assetId": "550e8400-e29b-41d4-a716-446655440003",
  "url": "https://r2.example.com/bucket/...",
  "fields": {
    "key": "uploads/user-id/asset-id-clip.mp4"
  }
}
```

**Status Codes**:
- `200` — URL generated
- `400` — Invalid MIME type or size
- `401` — Unauthorized

---

### `POST /uploads/:assetId/complete`

Mark an upload as complete and trigger metadata probing.

**Auth**: Required

**Path Parameters**:
- `assetId` (string, UUID) — Asset ID from presigned request

**Request Body**:
```json
{
  "sizeBytes": 52428800
}
```

**Validation Rules**:
- `sizeBytes`: Required, integer, must be positive

**Response**:
```json
{
  "asset": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "type": "clip",
    "filename": "clip.mp4",
    "mimeType": "video/mp4",
    "sizeBytes": 52428800,
    "durationSec": 15.5,
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "storageKey": "uploads/user-id/asset-id-clip.mp4",
    "createdAt": "2025-01-15T10:30:00Z"
  }
}
```

**Status Codes**:
- `200` — Asset processed
- `400` — Invalid size
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Asset not found

---

### `GET /uploads/:assetId`

Get asset metadata.

**Auth**: Required

**Path Parameters**:
- `assetId` (string, UUID) — Asset ID

**Response**:
```json
{
  "asset": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "type": "clip",
    "filename": "clip.mp4",
    "mimeType": "video/mp4",
    "sizeBytes": 52428800,
    "durationSec": 15.5,
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "storageKey": "uploads/user-id/asset-id-clip.mp4",
    "metadata": {
      "codec": "h264",
      "bitrate": 5000000,
      "colorSpace": "bt709"
    },
    "createdAt": "2025-01-15T10:30:00Z"
  }
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Asset not found

---

### `POST /uploads/:assetId/probe`

Probe asset metadata (force re-probe).

**Auth**: Required

**Path Parameters**:
- `assetId` (string, UUID) — Asset ID

**Response**:
```json
{
  "asset": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "durationSec": 15.5,
    "width": 1920,
    "height": 1080,
    "fps": 30
  }
}
```

**Status Codes**:
- `200` — Probed successfully
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Asset not found

---

## Renders

### `POST /renders`

Start a new render job for a project.

**Auth**: Required
**Rate Limit**: 3 requests per minute

**Request Body**:
```json
{
  "projectId": "550e8400-e29b-41d4-a716-446655440000",
  "options": {
    "resolution": "1080p",
    "quality": "high"
  }
}
```

**Validation Rules**:
- `projectId`: Required, string, valid UUID
- `options`: Optional, object

**Response**:
```json
{
  "job": {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "projectId": "550e8400-e29b-41d4-a716-446655440000",
    "status": "queued",
    "stage": "queued",
    "progress": 0,
    "workflowId": "video-render-workflow-abc123",
    "createdAt": "2025-01-15T10:30:00Z"
  }
}
```

**Status Codes**:
- `200` — Render queued
- `400` — Invalid request
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Project not found
- `409` — Render already in progress for this project
- `422` — Project missing required assets (reference or song)

**Side Effects**:
- Creates render record in database
- Starts Temporal workflow
- Enqueues job to Redis priority queue
- Updates project status to `rendering`

---

### `GET /renders/:jobId`

Get a render job by ID.

**Auth**: Required

**Path Parameters**:
- `jobId` (string, UUID) — Render job ID

**Response**:
```json
{
  "job": {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "projectId": "550e8400-e29b-41d4-a716-446655440000",
    "status": "running",
    "stage": "rendering",
    "progress": 65,
    "workflowId": "video-render-workflow-abc123",
    "outputAssetId": null,
    "previewAssetId": null,
    "errorMessage": null,
    "startedAt": "2025-01-15T10:30:00Z",
    "completedAt": null,
    "createdAt": "2025-01-15T10:30:00Z",
    "project": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "My Project"
    }
  }
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Job not found

---

### `GET /renders/project/:projectId`

List all render jobs for a project.

**Auth**: Required

**Path Parameters**:
- `projectId` (string, UUID) — Project ID

**Response**:
```json
{
  "jobs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440005",
      "status": "complete",
      "stage": "complete",
      "progress": 100,
      "outputAssetId": "550e8400-e29b-41d4-a716-446655440006",
      "completedAt": "2025-01-15T10:45:00Z",
      "createdAt": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized
- `403` — Forbidden

---

### `POST /renders/:jobId/complete`

Worker webhook to mark a render as complete or failed.

**Auth**: Required (worker authentication)

**Path Parameters**:
- `jobId` (string, UUID) — Render job ID

**Request Body**:
```json
{
  "status": "complete",
  "outputAssetId": "550e8400-e29b-41d4-a716-446655440006",
  "previewAssetId": "550e8400-e29b-41d4-a716-446655440007"
}
```

Or for failures:
```json
{
  "status": "failed",
  "errorMessage": "Encoder error: out of memory"
}
```

**Validation Rules**:
- `status`: Required, enum `complete | failed`
- `outputAssetId`: Optional, string, valid UUID
- `previewAssetId`: Optional, string, valid UUID
- `errorMessage`: Optional, string, max 2000 characters

**Response**:
```json
{
  "job": {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "status": "complete",
    "outputAssetId": "550e8400-e29b-41d4-a716-446655440006",
    "completedAt": "2025-01-15T10:45:00Z"
  }
}
```

**Status Codes**:
- `200` — Updated successfully
- `400` — Invalid request body
- `401` — Unauthorized
- `404` — Job not found

**Side Effects**:
- Updates render record
- Updates project status (`complete` or `failed`)

---

## Internal

> Routes under `/api/internal` are for worker-to-API communication only. All requests must include the header `x-internal-token: <INTERNAL_WORKER_TOKEN>`.

### `POST /internal/user-events`

Record a user-facing event from a worker (e.g. pipeline stage changes).

**Auth**: `x-internal-token`

**Request Body**:
```json
{
  "userId": "550e8400-e29b-41d4-a716-446655440000",
  "code": "RENDER_STARTED",
  "message": "Render workflow started",
  "details": { "projectId": "..." },
  "route": "/api/internal/..."
}
```

**Response**:
```json
{
  "ok": true
}
```

---

### `GET /internal/projects/:id`

Fetch project data needed by the render worker.

**Auth**: `x-internal-token`

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Response**:
```json
{
  "project": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "userId": "550e8400-e29b-41d4-a716-446655440001",
    "name": "My Project",
    "status": "rendering",
    "styleTier": "full_remix",
    "mode": "auto",
    "referenceAssetId": "550e8400-e29b-41d4-a716-446655440002",
    "songAssetId": "550e8400-e29b-41d4-a716-446655440003",
    "clipAssetIds": ["550e8400-e29b-41d4-a716-446655440004"],
    "cutList": { /* ... */ },
    "renderAssetId": null,
    "createdAt": "2025-01-15T10:30:00Z",
    "updatedAt": "2025-01-15T10:30:00Z"
  },
  "assets": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440004",
      "projectId": "550e8400-e29b-41d4-a716-446655440000",
      "type": "clip",
      "filename": "clip.mp4",
      "mimeType": "video/mp4",
      "sizeBytes": 52428800,
      "durationSec": 15.5,
      "width": 1920,
      "height": 1080,
      "fps": 30,
      "storageKey": "uploads/.../clip.mp4",
      "storageUrl": "https://...",
      "metadata": {}
    }
  ],
  "activeRender": {
    "id": "550e8400-e29b-41d4-a716-446655440005",
    "status": "running",
    "stage": "rendering",
    "progress": 45,
    "workflowId": "video-render-workflow-abc123"
  }
}
```

**Status Codes**:
- `200` — Success
- `401` — Missing or invalid internal token
- `404` — Project not found

---

### `POST /internal/assets`

Create an output asset row for worker-generated outputs (render, LUT, etc.).

**Auth**: `x-internal-token`

**Request Body**:
```json
{
  "projectId": "550e8400-e29b-41d4-a716-446655440000",
  "type": "render",
  "filename": "output.mp4",
  "mimeType": "video/mp4"
}
```

**Validation Rules**:
- `projectId`: Required, valid UUID
- `type`: Required, enum `reference_video | song | clip | render | subtitle | lut | sfx`
- `filename`: Required, string, max 255 characters
- `mimeType`: Required, string, max 100 characters

**Response**:
```json
{
  "assetId": "550e8400-e29b-41d4-a716-446655440006",
  "storageKey": "projects/550e8400-.../render/550e8400-...-output.mp4",
  "asset": { /* full asset row */ }
}
```

**Status Codes**:
- `200` — Created successfully
- `401` — Missing or invalid internal token
- `404` — Project not found

---

### `PATCH /internal/assets/:assetId/probe`

Update asset metadata after ffprobe (used by the ingest worker).

**Auth**: `x-internal-token`

**Path Parameters**:
- `assetId` (string, UUID) — Asset ID

**Request Body** (all fields optional):
```json
{
  "durationSec": 15.5,
  "width": 1920,
  "height": 1080,
  "fps": 30
}
```

**Response**:
```json
{
  "asset": {
    "id": "550e8400-e29b-41d4-a716-446655440003",
    "durationSec": 15.5,
    "width": 1920,
    "height": 1080,
    "fps": 30
  }
}
```

**Status Codes**:
- `200` — Updated successfully
- `401` — Missing or invalid internal token
- `404` — Asset not found

---

### `PATCH /internal/assets/:assetId/complete`

Finalize a worker-generated asset with size and public URL.

**Auth**: `x-internal-token`

**Path Parameters**:
- `assetId` (string, UUID) — Asset ID

**Request Body**:
```json
{
  "sizeBytes": 52428800,
  "storageUrl": "https://r2.example.com/...",
  "metadata": { "codec": "h264" }
}
```

**Validation Rules**:
- `sizeBytes`: Required, integer, 0–5 GB
- `storageUrl`: Optional, valid URL
- `metadata`: Optional, object

**Response**:
```json
{
  "asset": {
    "id": "550e8400-e29b-41d4-a716-446655440006",
    "sizeBytes": 52428800,
    "storageUrl": "https://r2.example.com/..."
  }
}
```

**Status Codes**:
- `200` — Updated successfully
- `401` — Missing or invalid internal token
- `404` — Asset not found

---

## Templates

### `GET /templates`

List templates (user's own + public).

**Auth**: Required

**Response**:
```json
{
  "templates": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440008",
      "name": "Cinematic Intro",
      "description": "A dramatic opening sequence",
      "cutList": { /* ... */ },
      "tags": ["intro", "cinematic"],
      "isPublic": true,
      "usageCount": 42,
      "userId": "550e8400-e29b-41d4-a716-446655440009",
      "createdAt": "2025-01-01T00:00:00Z",
      "updatedAt": "2025-01-10T00:00:00Z"
    }
  ]
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized

---

### `POST /templates`

Create a template from a cutlist.

**Auth**: Required

**Request Body**:
```json
{
  "name": "My Template",
  "description": "A template for travel videos",
  "cutList": {
    "globals": { "totalDurationS": 30 },
    "slots": []
  },
  "tags": ["travel"],
  "isPublic": false
}
```

**Validation Rules**:
- `name`: Required, string, max 200 characters
- `description`: Optional, string, max 1000 characters
- `cutList`: Required, object
- `tags`: Optional, array of strings
- `isPublic`: Optional, boolean, defaults to `false`

**Response**:
```json
{
  "template": {
    "id": "550e8400-e29b-41d4-a716-446655440008",
    "name": "My Template",
    "description": "A template for travel videos",
    "cutList": { /* ... */ },
    "tags": ["travel"],
    "isPublic": false,
    "usageCount": 0,
    "createdAt": "2025-01-15T10:30:00Z"
  }
}
```

**Status Codes**:
- `200` — Created successfully
- `400` — Invalid request body
- `401` — Unauthorized

---

### `GET /templates/:id`

Get a template by ID.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Template ID

**Response**:
```json
{
  "template": {
    "id": "550e8400-e29b-41d4-a716-446655440008",
    "name": "Cinematic Intro",
    "description": "A dramatic opening sequence",
    "cutList": { /* ... */ },
    "tags": ["intro", "cinematic"],
    "isPublic": true,
    "usageCount": 42,
    "userId": "550e8400-e29b-41d4-a716-446655440009",
    "createdAt": "2025-01-01T00:00:00Z",
    "updatedAt": "2025-01-10T00:00:00Z"
  }
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized
- `403` — Forbidden (private template of another user)
- `404` — Template not found

---

### `PATCH /templates/:id`

Update a template.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Template ID

**Request Body** (all fields optional):
```json
{
  "name": "Updated Template Name",
  "isPublic": true
}
```

**Response**:
```json
{
  "template": {
    "id": "550e8400-e29b-41d4-a716-446655440008",
    "name": "Updated Template Name",
    "isPublic": true,
    "updatedAt": "2025-01-15T11:00:00Z"
  }
}
```

**Status Codes**:
- `200` — Updated successfully
- `401` — Unauthorized
- `403` — Forbidden (not the owner)
- `404` — Template not found

---

### `DELETE /templates/:id`

Delete a template.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Template ID

**Response**:
```json
{
  "success": true
}
```

**Status Codes**:
- `200` — Deleted successfully
- `401` — Unauthorized
- `403` — Forbidden
- `404` — Template not found

---

### `POST /templates/:id/apply`

Apply a template to the current project.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Template ID

**Response**:
```json
{
  "cutList": {
    "globals": { "totalDurationS": 30 },
    "slots": []
  }
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized
- `403` — Forbidden (private template of another user)
- `404` — Template not found

**Side Effects**:
- Increments template `usageCount`

---

## Settings

### `GET /settings/provider-keys`

List the authenticated user's provider API keys.

**Auth**: Required

**Response**:
```json
{
  "keys": [
    {
      "provider": "anthropic",
      "maskedKey": "sk-ant-...abcd",
      "createdAt": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized

**Notes**:
- Keys are masked (only last 4 characters shown)
- Actual key values are never returned

---

### `POST /settings/provider-keys`

Store a provider API key.

**Auth**: Required

**Request Body**:
```json
{
  "provider": "anthropic",
  "key": "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx"
}
```

**Validation Rules**:
- `provider`: Required, enum `anthropic | openai | gemini | groq`
- `key`: Required, string, min 10 characters

**Response**:
```json
{
  "success": true
}
```

**Status Codes**:
- `200` — Stored successfully
- `400` — Invalid request body
- `401` — Unauthorized

**Notes**:
- Key is encrypted at rest before storage
- Overwrites existing key for the same provider

---

### `DELETE /settings/provider-keys/:provider`

Delete a provider API key.

**Auth**: Required

**Path Parameters**:
- `provider` (string) — Provider name

**Response**:
```json
{
  "success": true
}
```

**Status Codes**:
- `200` — Deleted successfully
- `401` — Unauthorized

---

### `POST /settings/provider-keys/test`

Test a provider API key.

**Auth**: Required

**Request Body**:
```json
{
  "provider": "anthropic"
}
```

**Response** (success):
```json
{
  "valid": true,
  "provider": "anthropic"
}
```

**Response** (failure):
```json
{
  "valid": false,
  "provider": "anthropic",
  "error": "Invalid API key"
}
```

**Status Codes**:
- `200` — Test completed (check `valid` field)
- `400` — Invalid request
- `401` — Unauthorized

---

## Presence

### `POST /presence/:id/presence`

Report cursor presence for a project.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Request Body**:
```json
{
  "x": 450,
  "y": 320,
  "name": "Alice"
}
```

**Validation Rules**:
- `x`: Required, number
- `y`: Required, number
- `name`: Optional, string

**Response**:
```json
{
  "success": true
}
```

**Status Codes**:
- `200` — Success
- `400` — Missing x or y coordinates
- `401` — Unauthorized

**Notes**:
- Cursor data expires after 15 seconds of inactivity
- Colors are deterministically assigned based on user ID

---

### `GET /presence/:id/presence`

Get active cursors for a project.

**Auth**: Required

**Path Parameters**:
- `id` (string, UUID) — Project ID

**Response**:
```json
{
  "users": [
    {
      "userId": "550e8400-e29b-41d4-a716-446655440010",
      "name": "Bob",
      "color": "#3b82f6",
      "x": 200,
      "y": 150
    }
  ]
}
```

**Status Codes**:
- `200` — Success
- `401` — Unauthorized

**Notes**:
- Automatically cleans up stale cursors (15s TTL)
- Does not include the requesting user's own cursor

---

## Progress

### `GET /progress/:jobId/events`

Subscribe to real-time render progress via Server-Sent Events (SSE).

**Auth**: Required

**Path Parameters**:
- `jobId` (string, UUID) — Render job ID

**Headers**:
- `Accept: text/event-stream`

**Event Stream Format**:
```
event: progress
data: {"stage":"rendering","progress":45,"message":"Applying transitions..."}

event: complete
data: {"stage":"complete","progress":100,"outputUrl":"https://r2.example.com/..."}

event: error
data: {"stage":"failed","error":"Encoder error"}
```

**Status Codes**:
- `200` — SSE stream opened
- `401` — Unauthorized
- `403` — Forbidden (job belongs to another user)
- `404` — Job not found

**Notes**:
- Connection is kept open until render completes or fails
- Frontend should implement auto-reconnect with exponential backoff
- Max 5 reconnection attempts recommended

---

## Error Codes Reference

| Code | Description | Typical HTTP Status |
|---|---|---|
| `UNAUTHORIZED` | Clerk JWT missing or invalid | 401 |
| `FORBIDDEN` | User does not own the resource | 403 |
| `NOT_FOUND` | Resource does not exist | 404 |
| `VALIDATION_ERROR` | Request body failed Zod validation | 422 |
| `MISSING_ASSETS` | Project missing required assets | 422 |
| `CONFLICT` | Render already in progress | 409 |
| `NO_CUTLIST` | Project has no cutlist for prompt editing | 400 |
| `PROVIDER_KEY_MISSING` | AI provider key not configured | 400 |
| `PROVIDER_INVALID_RESPONSE` | AI provider returned 401/403 | 500 |
| `PROVIDER_RATE_LIMITED` | AI provider rate limit hit | 500 |
| `TEMPORAL_ERROR` | Temporal workflow failed to start | 500 |
| `INTERNAL_ERROR` | Unhandled server error | 500 |

---

## Log Ingestion

### `POST /api/log`

Ingests batched frontend log events. Used by the web client's structured logger.

**Auth**: Required

**Request Body**:
```json
{
  "events": [
    {
      "level": "error",
      "message": "Failed to load project",
      "context": { "projectId": "abc-123" },
      "ts": 1717689600000,
      "url": "/editor/abc-123"
    }
  ]
}
```

**Validation Rules**:
- `level`: Required, enum `["debug", "info", "warn", "error"]`
- `message`: Required, string, max 2000 chars
- `context`: Optional, record of unknown values
- `ts`: Required, number (Unix timestamp ms)
- `url`: Required, string, max 500 chars

**Response**:
```json
{
  "ok": true
}
```

**Status Codes**:
- `200` — Events ingested
- `400` — Invalid batch format
- `401` — Unauthorized

**Notes**:
- Client sends batches automatically every 5 seconds or when buffer reaches 10 events
- Uses `keepalive: true` to survive page navigation

---

## Rate Limits

| Endpoint | Limit | Window |
|---|---|---|
| `POST /renders` | 3 | 1 minute |
| `POST /projects/:id/transcribe` | 5 | 1 minute |
| `POST /projects/:id/prompt` | 10 | 1 minute |
| All other endpoints | 60 | 1 minute |

Rate limit responses include:
```json
{
  "error": "Rate limit exceeded",
  "code": "RATE_LIMITED",
  "retryAfter": 45
}
```
