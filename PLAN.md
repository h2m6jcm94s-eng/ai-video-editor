# AI Video Editor — Backend Completion Plan

## Goal
Complete the backend/worker layer so the pipeline runs end-to-end via CLI and API, with all real AI service integrations wired up. The frontend stays basic (user will provide design later).

## Current State Assessment

### What's Built (working code exists)
- Monorepo scaffolding (pnpm + uv workspaces)
- Shared TypeScript types and Python Pydantic models
- Fastify API skeleton with in-memory stores
- Next.js web app with basic upload/timeline UI
- **Ingest worker**: PyAV probe, PySceneDetect shot detection, TransNet V2 integration, allin1/librosa beat detection, energy curve
- **Style worker**: LUT extraction (color-matcher → .cube), transition classifier (cut/dissolve/wipe/whip), PaddleOCR text extraction, camera motion analysis (optical flow + affine)
- **Reason worker**: Claude forced tool-use cut-list generation with JSON schema, programmatic fallback, weighted clip ranking with diversity/MMR
- **Render worker**: FFmpeg filter_complex compiler with xfade transitions, lut3d, drawtext overlays, audio sync
- **Upscale worker**: Real-ESRGAN ncnn-vulkan frame processor, Topaz Video AI API client
- Temporal workflow definitions, Modal deployment scripts, Docker Compose, CLI orchestrator

### What's Missing / Stubbed
1. **Database layer** — projects/assets use in-memory Maps; need Neon Postgres + Drizzle schema
2. **Real AI API integrations** — Claude, Gemini, Twelve Labs have graceful fallbacks but don't actually call APIs when keys are present
3. **R2 storage** — presigned URL logic exists but no actual multipart upload completion, download, or lifecycle
4. **Temporal workers** — workflow definitions exist but no running worker binaries that poll the queue
5. **Qdrant vector DB** — no actual embedding storage/search (Marengo/SigLIP-2 shadow not wired)
6. **API completeness** — missing ffprobe metadata extraction on upload, missing render trigger endpoint, no job status polling
7. **Error handling / retries / observability** — subprocess calls don't capture stderr, no structured logging
8. **Clerk auth** — not wired into API routes

---

## AI Provider Abstraction Layer (NEW)

### Prompts Are Provider-Agnostic
Yes — the prompts, system instructions, JSON schemas, and analysis context remain **exactly the same** regardless of which AI provider you use. Whether it's Claude, Gemini, Kimi, Groq, or OpenRouter, the prompt engineering is identical. What changes is:
1. The HTTP client / SDK used to send the request
2. The response parsing logic
3. Minor adapter differences (e.g., tool-use vs function-calling vs JSON mode)

### Unified Provider Interface
We will build a single `AIProvider` abstract class in `shared-py` with these methods:
- `generate_cutlist(context: str, schema: dict) -> CutList` — all providers
- `classify_shot(keyframes: list, schema: dict) -> ShotAnalysis` — all providers
- `analyze_style(reference_desc: str) -> StyleAnalysis` — all providers

### Supported Providers (swappable via env var)
| Provider | Model | Why Use It | Secret Key |
|----------|-------|-----------|------------|
| **Anthropic Claude** | Sonnet 4.6 | Best tool-use reliability, 1M context | `ANTHROPIC_API_KEY` |
| **Google Gemini** | 2.5 Pro/Flash | Best free tier, native video input | `GEMINI_API_KEY` |
| **Moonshot Kimi** | k1.5 | Long context (2M tokens), strong reasoning | `KIMI_API_KEY` |
| **Groq** | Llama 3.3 70B / Mixtral | Ultra-fast inference (~800 tok/s), cheap | `GROQ_API_KEY` |
| **OpenRouter** | Any model (Claude/GPT/etc) | Universal gateway, pay-as-you-go, no lock-in | `OPENROUTER_API_KEY` |
| **OpenAI** | GPT-4o / o3-mini | Good JSON mode, widely known | `OPENAI_API_KEY` |

**Switching providers**: Just change `AI_PROVIDER=claude` to `AI_PROVIDER=kimi` in `secrets.env`. Zero code changes.

### Why This Matters
- You can start with **Groq** (fast, cheap, no rate limit headaches) for development
- Switch to **Claude** for production cut-list quality
- Use **Kimi** for long-context style analysis (2M tokens vs Claude's 1M)
- Fall back to **Gemini** if another provider is down
- All without changing a single prompt or JSON schema

---

## Complete Service Cost Breakdown

### 1. Claude (Anthropic) — Cut-List Generation
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ❌ No free tier | Must add a credit card to get API access |
| **Minimal** | ~$0.07–$0.15 per render | Sonnet 4.6: $3/MTok input, $15/MTok output. Cut-list prompt ~8k cached + 3k fresh + 4k out |
| **Alternative** | **Programmatic fallback (FREE)** | Already built — generates beat-synced cut-list without any LLM. Lower quality but zero cost |
| **Alternative** | **Groq Llama 3.3 70B (~$0.01/render)** | $0.59/MTok input, $0.79/MTok output. 99% cheaper than Claude |
| **Alternative** | **Kimi k1.5 (~$0.02/render)** | $2/MTok input, $8/MTok output. 2M context window |
| **Cost lever** | Prompt caching = 90% off cached reads; Batch API = 50% off | Cache the system prompt + schema once, reuse for warm renders |

- **Pricing**: https://www.anthropic.com/pricing
- **Secret needed**: `ANTHROPIC_API_KEY`
- **Recommendation**: Start with Groq or programmatic fallback (FREE). Add Claude later when you need higher-quality edits.

---

### 2. Google Gemini — Shot Classification + Style Analysis
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ 1,500 requests/day (Flash) | Flash: 15 RPM, 1M tokens/day; Pro: 2 RPM, 50K tokens/day |
| **Minimal** | ~$0.005–$0.02 per render | Flash: $0.50/MTok input, $3/MTok output (video). ~40 shots × 2s each |
| **Alternative** | **Self-host Qwen2.5-VL-7B (FREE after GPU cost)** | Run on Modal L4 (~$0.80/hr) or local GPU. One-time setup, then free inference |
| **Alternative** | **Groq (~$0.002/render)** | Llama 3.2 Vision on Groq. Fast and cheap |
| **Cost lever** | Batch API = 50% off; context caching = 90% off | Gemini free tier is genuinely generous for MVP |

- **Pricing**: https://ai.google.dev/pricing
- **Secret needed**: `GEMINI_API_KEY`
- **Recommendation**: Use Gemini Flash free tier for development. Paid tier is cheap enough for production MVP.

---

### 3. Moonshot Kimi — Long-Context Style Analysis + Cut-List
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ 1M tokens free trial | New accounts get trial credits |
| **Minimal** | ~$0.02–$0.05 per render | k1.5: $2/MTok input, $8/MTok output. 2M context window beats Claude's 1M |
| **Alternative** | **Claude Sonnet (same prompt, different price)** | Drop-in replacement via our abstraction layer |
| **Why Kimi** | 2M token context = can ingest entire reference analysis + all keyframes in one call | Best for long reference videos (>5 min) |

- **Pricing**: https://platform.moonshot.cn/pricing
- **Secret needed**: `KIMI_API_KEY`
- **Recommendation**: Use Kimi for long-context tasks (style analysis of 10+ min references). Use Claude/Groq for cut-list generation.

---

### 4. Groq — Fast Inference (Development Workhorse)
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ 1M tokens/day | Rate limited but enough for development |
| **Minimal** | ~$0.001–$0.01 per render | Llama 3.3 70B: $0.59/MTok input, $0.79/MTok output. Fastest inference on market |
| **Alternative** | **Any provider (swappable)** | Our abstraction layer makes Groq ↔ Claude ↔ Kimi a one-line config change |
| **Why Groq** | ~800 tokens/sec inference speed. No cold starts. Pay-as-you-go. | Perfect for rapid iteration during development |

- **Pricing**: https://groq.com/pricing
- **Secret needed**: `GROQ_API_KEY`
- **Recommendation**: Use Groq as your default provider during development. Switch to Claude/Kimi for production quality.

---

### 5. OpenRouter — Universal Gateway (No Lock-In)
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ Some models free with rate limits | Acts as a proxy to 100+ models |
| **Minimal** | Same as underlying model + small fee | $0.001/1k tokens routing fee. Access Claude, GPT, Llama, etc from one API key |
| **Alternative** | **Direct provider APIs** | Use OpenRouter to test which model works best, then switch to direct API for volume |
| **Why OpenRouter** | One key = 100 models. Automatic failover. No vendor lock-in. | Best for experimentation phase |

- **Pricing**: https://openrouter.ai/docs#models
- **Secret needed**: `OPENROUTER_API_KEY`
- **Recommendation**: Get an OpenRouter key first. Test Claude vs GPT vs Llama vs Kimi with the SAME prompt. Pick the winner. Then get a direct key for that provider.

---

### 6. Twelve Labs Marengo — Video Embeddings & Semantic Search
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ 600 minutes free | No credit card required. Indexes expire after 90 days |
| **Minimal** | ~$0.25 per render | $0.042/min indexing + $0.0015/min/mo storage + $4/1k searches. 4 min video + 20 queries |
| **Alternative** | **Self-host SigLIP-2 + Qdrant (FREE after infra)** | SigLIP-2 on HuggingFace (~50× cheaper). Qdrant free cloud: 1GB |
| **Cost lever** | Self-hosting drops from $0.25/render → ~$0.01/render | Biggest COGS lever at scale |

- **Pricing**: https://www.twelvelabs.io/pricing
- **Secret needed**: `TWELVE_LABS_API_KEY`
- **Recommendation**: Start with Twelve Labs free tier (600 min). Self-host SigLIP-2 + Qdrant once you hit scale.

---

### 7. Cloudflare R2 — Object Storage (Uploads + Renders)
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ 10 GB/mo + 1M Class A + 10M Class B ops | Perpetual free tier (not 12-month trial) |
| **Minimal** | ~$0.01–$0.05 per project | $0.015/GB-month storage. Zero egress fees |
| **Alternative** | **Local disk / MinIO (FREE)** | For local dev only. MinIO is S3-compatible self-hosted |
| **Cost lever** | Zero egress = saves $$$ vs S3 at scale | At 1TB + 10TB delivered: R2 = $15/mo vs S3 = $900+/mo |

- **Pricing**: https://developers.cloudflare.com/r2/pricing/
- **Secrets needed**: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- **Recommendation**: R2 free tier is plenty for MVP. Zero egress is the killer feature.

---

### 8. Neon Postgres — Database
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ 100 CU-hours/mo + 0.5 GB/project | 100 projects, 10 branches each. Scale-to-zero |
| **Minimal** | ~$5–$15/mo | Launch tier: $0.106/CU-hour, $0.35/GB-month. Pay only for active compute |
| **Alternative** | **SQLite / local Postgres (FREE)** | For local dev only. SQLite is file-based, zero ops |
| **Cost lever** | Scale-to-zero = $0 when idle | Perfect for bursty video editing workloads |

- **Pricing**: https://neon.tech/pricing
- **Secret needed**: `DATABASE_URL`
- **Recommendation**: Neon free tier handles MVP easily. Upgrade to Launch when you need >0.5GB.

---

### 9. Clerk — Authentication
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ 10,000 MAUs | Pre-built React components, JWT verification, social login |
| **Minimal** | $25/mo base + $0.02/MAU after 10K | Pro plan adds custom domains, MFA, organizations |
| **Alternative** | **Better Auth / Auth.js (FREE, self-hosted)** | Open source, GDPR-ready, but you build your own UI (1–3 days) |
| **Cost lever** | WorkOS = 1M MAU free for user management | Clerk is fastest to ship; Better Auth is cheapest at scale |

- **Pricing**: https://clerk.com/pricing
- **Secrets needed**: `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`
- **Recommendation**: Clerk free tier is fine for MVP. Switch to Better Auth if you hit 10K MAU and want to save $$$.

---

### 10. Redis — Cache / Queue / Pub-Sub
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ Upstash Redis = 10k cmds/day | Serverless Redis, no credit card needed |
| **Minimal** | ~$5/mo | Upstash paid: ~$0.20 per 100k commands |
| **Alternative** | **Local Redis (FREE)** | `docker run redis:7-alpine`. For local dev only |
| **Cost lever** | Self-hosted Redis = $0 | Docker Compose already includes Redis |

- **Pricing**: https://upstash.com/pricing/redis
- **Secret needed**: `REDIS_URL`
- **Recommendation**: Use local Redis via Docker Compose for dev. Upstash free tier for staging.

---

### 11. Modal — GPU Compute (Serverless)
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ $30/mo credits | 3 workspace seats, 10 concurrent GPUs |
| **Minimal** | ~$0.05–$0.15 per upscale job | L4: $0.80/hr ($0.000222/sec). A 60s upscale = ~$0.004 |
| **Alternative** | **RunPod / Lambda Labs (~40–60% cheaper)** | RunPod Pods for sustained workloads. Lambda: $0.75/hr A10G |
| **Cost lever** | Utilization <40% → Modal; >40% → RunPod/Lambda | Modal wins on cold starts; RunPod wins on sustained batch |

- **Pricing**: https://modal.com/pricing
- **Secrets needed**: `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`
- **Recommendation**: Modal free tier ($30/mo) covers MVP testing. Modal's sub-second cold starts are worth it for bursty video workloads.

---

### 12. Temporal — Workflow Orchestration
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ✅ Self-hosted = $0 | Temporal server runs in Docker. No limits |
| **Minimal** | ~$100/mo | Temporal Cloud starter plan. Managed, no ops |
| **Alternative** | **BullMQ / Inngest (cheaper but less durable)** | BullMQ = Redis-backed, no durability. Inngest = $0 starter |
| **Cost lever** | Self-hosted Temporal = free forever | Docker Compose can include Temporal server |

- **Pricing**: https://temporal.io/pricing
- **Secret needed**: `TEMPORAL_HOST` (no API key for self-hosted)
- **Recommendation**: Self-host Temporal via Docker Compose for MVP. Upgrade to Cloud when you need SLAs.

---

### 13. Topaz Video AI — Pro-Tier Upscaling (Optional)
| Tier | Cost | Details |
|------|------|---------|
| **Free** | ❌ No free tier | Must purchase license or use API |
| **Minimal** | $0.42–$1.00 per video | API pass-through pricing |
| **Alternative** | **Real-ESRGAN (FREE)** | Already built. Open source, runs on Modal L4. $0.05–$0.15/min |
| **Cost lever** | Real-ESRGAN = 4–10× cheaper | Quality gap is small at 720p→1080p. Topaz only wins at 4K |

- **Pricing**: https://www.topazlabs.com/pricing
- **Secret needed**: `TOPAZ_API_KEY` (optional)
- **Recommendation**: Skip Topaz for MVP. Real-ESRGAN is good enough. Add Topaz as a Pro upsell later.

---

## Per-Render Cost Summary (60s output)

### 💰 Zero-Cost Stack (FREE everything)
| Component | Cost |
|-----------|------|
| Cut-list generation | $0 (programmatic) |
| Shot classification | $0 (skip or use free Gemini/Groq tier) |
| Embeddings/search | $0 (skip semantic search) |
| Storage | $0 (R2 free tier) |
| Database | $0 (Neon free tier) |
| Auth | $0 (Clerk free tier) |
| GPU compute | $0 (Modal free credits) |
| **Total per render** | **$0.00** |

### 🪙 Minimal-Cost Stack (paid APIs for quality)
| Component | Cost |
|-----------|------|
| Claude Sonnet cut-list | ~$0.07 |
| Gemini Flash shot class | ~$0.01 |
| Twelve Labs indexing | ~$0.17 |
| Twelve Labs search | ~$0.08 |
| R2 storage/egress | ~$0.01 |
| Neon DB | ~$0.01 |
| Modal L4 render | ~$0.01 |
| **Total per render** | **~$0.36** |

### 🚀 Groq-Powered Stack (fast + cheap)
| Component | Cost |
|-----------|------|
| Groq Llama 3.3 70B cut-list | ~$0.01 |
| Groq vision shot class | ~$0.002 |
| Skip embeddings | $0 |
| R2 storage | ~$0.01 |
| Neon DB | ~$0.01 |
| Modal L4 render | ~$0.01 |
| **Total per render** | **~$0.05** |

### 🏆 Recommended Starting Point
Start with the **Groq-Powered Stack** for development. It's 7× cheaper than Claude and inference is ~800 tok/sec (no waiting). When you're ready for production, swap `AI_PROVIDER=groq` → `AI_PROVIDER=claude` in one line.

---

## Implementation Plan

### Phase 1: AI Provider Abstraction Layer
- Create `services/shared-py/src/shared_py/ai_providers/__init__.py`
- Create `base.py` with abstract class `AIProvider`:
  - `generate_cutlist(context: str, schema: dict) -> CutList`
  - `classify_shot(keyframes: list, schema: dict) -> ShotAnalysis`
  - `analyze_style(reference_desc: str) -> StyleAnalysis`
- Create concrete implementations:
  - `claude_provider.py` — Anthropic SDK, forced tool-use
  - `gemini_provider.py` — Google GenAI SDK, responseSchema
  - `kimi_provider.py` — Moonshot OpenAI-compatible API
  - `groq_provider.py` — Groq OpenAI-compatible API
  - `openrouter_provider.py` — OpenRouter universal gateway
  - `openai_provider.py` — OpenAI native SDK
- Factory function: `get_ai_provider(provider_name: str) -> AIProvider`
- All providers use the **same prompt templates** and **same JSON schemas**

### Phase 2: Secrets & Environment
Create `secrets.env` at repo root:

```bash
# === AI Provider Selection ===
# Options: claude | gemini | kimi | groq | openrouter | openai | programmatic
AI_PROVIDER=groq

# === AI API Keys (provide at least one matching AI_PROVIDER) ===
ANTHROPIC_API_KEY=          # Claude cut-list
GEMINI_API_KEY=             # Gemini shot classification
KIMI_API_KEY=               # Moonshot Kimi long-context analysis
GROQ_API_KEY=               # Groq fast inference (recommended for dev)
OPENROUTER_API_KEY=         # Universal gateway - try any model
OPENAI_API_KEY=             # OpenAI GPT-4o / o3-mini

# === Storage (R2) ===
R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=           # Required for cloud storage
R2_SECRET_ACCESS_KEY=       # Required for cloud storage
R2_BUCKET_NAME=ai-video-editor

# === Database ===
DATABASE_URL=               # Required. Use Neon free tier or local: postgresql://localhost:5432/ave

# === Cache / Queue ===
REDIS_URL=redis://localhost:6379  # Required. Use local Redis or Upstash

# === Auth ===
CLERK_SECRET_KEY=           # Optional - skip auth for MVP
CLERK_PUBLISHABLE_KEY=      # Optional - skip auth for MVP

# === Infrastructure ===
TEMPORAL_HOST=localhost:7233
MODAL_TOKEN_ID=             # Optional - only if deploying to Modal
MODAL_TOKEN_SECRET=         # Optional - only if deploying to Modal

# === Pro-tier upscaling (optional) ===
TOPAZ_API_KEY=              # Optional - Real-ESRGAN is default
```

### Phase 3: Database Layer (Neon + Drizzle)
- Add `apps/api/src/db/schema.ts` with tables: `users`, `projects`, `assets`, `renders`, `cut_lists`
- Add `apps/api/src/db/index.ts` with Drizzle client using `DATABASE_URL`
- Replace all in-memory `Map` stores in API routes with Drizzle queries
- Add migration script

### Phase 4: Wire Real AI APIs via Abstraction Layer
- Refactor `reason-worker/cutlist_gen.py` to use `get_ai_provider(os.environ.get("AI_PROVIDER", "programmatic"))`
- Refactor `style-worker` to use AI provider for shot classification and style analysis
- Add retry logic with exponential backoff for all API calls
- Add circuit breaker pattern for external APIs
- All providers use identical prompts and schemas

### Phase 5: R2 Storage Integration
- Add download helper in `storage.ts`: `downloadAsset(storageKey, localPath)`
- Add multipart upload completion helper that validates ETags
- Add lifecycle: auto-delete reference video bytes after 24h (retain only extracted JSON features)
- Wire upload completion to trigger async ffprobe metadata extraction

### Phase 6: Temporal Workers
- Canonical render worker lives in `services/render-worker/` (fetches project, downloads assets, compiles, uploads, completes)
- Add `apps/api/src/services/temporal.ts` — client to start workflows from API
- Wire `POST /api/renders` to start a `VideoRenderWorkflow` on `video-render-queue`
- Ingest/style/reason workers live in `services/` and are triggered by upload / API events, not by the render worker

### Phase 7: API Completeness
- Add ffprobe endpoint: `POST /api/uploads/:assetId/probe` that downloads from R2, runs PyAV probe, stores metadata
- Add render trigger with proper job tracking in DB
- Add `GET /api/jobs/:id` for status polling (fallback to SSE)
- Add webhook/endpoint for Modal job callbacks

### Phase 8: Testing & Validation
- Unit tests for each AI provider adapter
- Integration test: full pipeline with mock video files
- End-to-end test: upload → analyze → generate cutlist → render → download
- Performance benchmark: measure render time per 60s output

---

## What I Need From the User

1. **Confirm the AI provider abstraction approach** — does the unified interface + swappable providers design work for you?
2. **Which provider do you want as default?** I recommend Groq for development (fast, cheap, good free tier) and Claude for production.
3. **Deployment target** — local Docker Compose for now, or do you want Modal GPU workers running immediately?

Once the plan is approved, I will:
1. Build the AI provider abstraction layer
2. Complete all backend wiring
3. Run integration tests
4. Then you fill in `secrets.env` and we test with real APIs
