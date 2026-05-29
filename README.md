# AI Video Editor - Reference Style Matching

> Parse a reference video's editing style and apply it to your clips, synced to a custom song.

## Overview

This AI video editor takes three inputs:
1. **Reference video** - The style you want to match (cut rhythm, shot types, color grade, transitions, text overlays)
2. **Your clips** - Your raw footage to be edited
3. **Your song** - The music to sync the edit to

It outputs a professionally edited video that mimics the reference's style while using your content.

## Architecture

```
repo/
├── apps/
│   ├── web/          # Next.js 15 frontend
│   └── api/          # Fastify 5 backend API
├── packages/
│   ├── shared-types/ # TypeScript type definitions
│   └── eslint-config # Shared linting rules
├── services/         # Python workers (uv workspace)
│   ├── ingest-worker/    # Video probe, shot detection, beat detection
│   ├── style-worker/     # LUT extraction, transition typing, text OCR
│   ├── reason-worker/    # Claude cut-list generation + clip ranking
│   ├── render-worker/    # FFmpeg timeline compiler
│   ├── upscale-worker/   # Real-ESRGAN / Topaz upscaling
│   └── shared-py/        # Shared Python models & config
├── infra/
│   ├── docker/       # Dockerfiles & compose
│   ├── modal/        # Modal.cloud GPU deployments
│   └── temporal/     # Temporal workflow definitions
└── services/orchestrator.py  # CLI pipeline runner
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Reference Understanding | TransNet V2 + Gemini 2.5 Pro + Twelve Labs Marengo 3 |
| Shot Classification | Gemini 2.5 Flash / Qwen2.5-VL |
| Beat Detection | allin1 + librosa |
| Color Grade | color-matcher + colour-science |
| Text OCR | PaddleOCR + Gemini Pro |
| Cut-List Reasoning | Claude Sonnet 4.6 (forced tool-use) |
| Render | FFmpeg + PyAV |
| Upscale | Real-ESRGAN (MVP) / Topaz Video AI (Pro) |
| Orchestration | Temporal Cloud |
| Storage | Cloudflare R2 + CDN |
| Auth | Clerk |
| DB | Neon Postgres + Qdrant |

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- pnpm
- uv
- FFmpeg

### Installation

```bash
# Install JS dependencies
pnpm install

# Install Python dependencies
uv sync

# Start local services
docker-compose -f infra/docker/docker-compose.yml up -d

# Run the API
pnpm --filter @ai-video-editor/api dev

# Run the web app
pnpm --filter @ai-video-editor/web dev
```

### CLI Usage

```bash
# Run the full pipeline from command line
uv run python services/orchestrator.py \
  --reference ./reference.mp4 \
  --song ./song.mp3 \
  --clips ./clip1.mp4 ./clip2.mp4 ./clip3.mp4 \
  --output ./final.mp4 \
  --tier full_style \
  --mode auto
```

### API Usage

```bash
# Create a project
curl -X POST http://localhost:4000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My Edit", "styleTier": "full_style", "mode": "auto"}'

# Upload assets (get presigned URL)
curl -X POST http://localhost:4000/api/uploads/presigned \
  -H "Content-Type: application/json" \
  -d '{"projectId": "...", "filename": "ref.mp4", "type": "reference_video"}'

# Start render
curl -X POST http://localhost:4000/api/renders \
  -H "Content-Type: application/json" \
  -d '{"projectId": "..."}'

# Stream progress
curl http://localhost:4000/api/progress/{jobId}/events
```

## Cost Model

Per 60-second output (quality tier):

| Component | Cost |
|-----------|------|
| TransNet V2 shot detection | ~$0.012 |
| Gemini style analysis | ~$0.029 (first) / $0.003 (cached) |
| Marengo 3 indexing | ~$0.168 |
| Claude cut-list | ~$0.074 |
| FFmpeg render | ~$0.005 |
| R2 storage/egress | ~$0.008 |
| **Total cold render** | **~$0.39** |
| **Total warm render** | **~$0.36** |

## Development Phases

- **Phase 0 (Week 1)**: Scaffolding, auth, uploads, Temporal hello-world
- **Phase 1 (Week 2)**: Basic render pipeline (hard-coded cut-list)
- **Phase 2 (Week 3-4)**: Claude cut-list + clip ranking (demo ready)
- **Phase 3 (Week 5)**: TransNet V2 + transitions
- **Phase 4 (Week 6)**: Color grade (LUT) extraction
- **Phase 5 (Week 7)**: Text overlay detection
- **Phase 6 (Week 8-9)**: Assisted mode UI + proxy preview
- **Phase 7 (Week 10-11)**: Effects + camera motion
- **Phase 8 (Week 12+)**: Upscale + polish

## License

MIT
