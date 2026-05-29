# Reference-style AI video editor: a complete MVP build plan

**You're building in a real gap.** As of April 2026, no shipping product takes a reference video + a user's own clips + a custom song and edits those clips in the reference's style. Adobe's Firefly "Quick Cut" (April 2026) is text-driven; CapCut's AI templates are hand-authored, not parsed from arbitrary references; Opus Clip, Submagic, Vizard, and Descript all pull highlights *from within* the user's footage; Runway, Pika, Kling, and Luma generate new pixels rather than re-editing existing ones. The workflow you're describing — parse a reference's cut rhythm, shot-type sequence, color grade, transitions, and overlays, then apply that to a user-supplied clip library synced to a custom song — is a real wedge. **The defensible moat is the reference-parsing pipeline plus the cut-list-as-a-contract between analysis and render.** Below is an implementable technical plan optimized for a competent SRE who wants to ship a demo in 4–6 weeks and a polished MVP in 10–12.

## Recommended stack at a glance

| Layer | Pick | Rationale |
|---|---|---|
| Reference video understanding | **TransNet V2 (PyTorch port)** + **Gemini 2.5 Pro** (cached) + **Twelve Labs Marengo 3** for embeddings | TransNet V2 is still the open-source SOTA for shot boundaries; Gemini Pro gives whole-video style analysis in one call with structured JSON; Marengo gives turnkey multimodal embeddings for clip↔slot matching |
| Shot classification on user clips | **Gemini 2.5 Flash** with `responseSchema` (or Qwen2.5-VL-7B self-hosted) | Flash at ~$0.0046/min is the quality/$ winner; Qwen2.5-VL is the best self-hosted fallback |
| Beat/downbeat/section/energy | **allin1** (primary) + **Beat This!** (cross-check) + `librosa.feature.rms` | allin1 is the only OSS lib that outputs beats + downbeats + labeled sections (verse/chorus/drop) + tempo in one call |
| Color grade transfer | **color-matcher** (HM-MVGD-HM) → identity cube → `.cube` via `colour-science` → FFmpeg `lut3d` filter | Proven pipeline, no training, produces a portable LUT |
| Text overlay extraction | **PaddleOCR** per-frame + **Gemini 2.5 Pro** for kinetic-text semantics | PaddleOCR handles detection/timing; Gemini classifies font, color, animation |
| Transition/effects/motion | **TransNet V2** gradual-prob head + **RAFT/Farneback** flow + affine decomposition | Classical flow plus TransNet is enough; pure-neural transition-type classifiers aren't shipped |
| Cut-list reasoning layer | **Claude Sonnet 4.6** (1M context) with **forced tool-use** for JSON schema | Cheapest/reliable structured output with extended thinking; no native video so we feed text analysis + keyframes |
| Render engine | **FFmpeg** (subprocess) + **PyAV** for probing | Frame accuracy, `lut3d`, `xfade`, `drawtext`, h264_nvenc — only path that supports LUTs + beat-exact cuts |
| Upscaler | **Real-ESRGAN-ncnn-vulkan** on Modal L4 (MVP) → **Topaz Video AI API** as Pro tier | $0.05–0.15/min vs $0.42–1.00/min; quality gap is masked by render-at-720p-then-upscale |
| Orchestration | **Temporal Cloud** (Python + TS SDKs) | Durable, signals for progress, Descript uses it for the same workload |
| Monorepo | **pnpm workspaces + Turborepo** (JS) + **uv workspaces** (Python) coexisting | 2025's DX winner; single git repo, two disjoint workspace tools |
| GPU compute | **Modal** (primary, bursty), **RunPod Pods** for sustained batch | Sub-second cold starts, per-second billing, Python-native |
| Storage + CDN | **Cloudflare R2 + Cloudflare CDN** | Zero egress — the deciding factor for video delivery |
| Uploads | **Uppy v4 + S3 multipart → R2** (presigned) | Simpler than running tusd; R2 supports S3 multipart natively |
| Progress | **SSE** via Node API, fed by Redis pub/sub from workers | One-way, auto-reconnect, no socket infra needed |
| Auth | **Clerk** | 10k MAU free, drop-in React components, ship in a day |
| DB | **Neon Postgres** + **Qdrant** (embeddings) | Serverless, cheap, zero-ops |

## 1. Video understanding layer

**Shot boundary detection.** Use **TransNet V2** via the maintained `transnetv2-pytorch` package (June 2025). It still holds SOTA on BBC/RAI/ClipShots for open-source (F1 ~0.96 BBC) and nothing has clearly surpassed it by April 2026. Run at 48×27 (the training resolution), ~100× real-time on an L4. Gate with a cheap PySceneDetect first pass to skip static regions — a pattern adopted by Summer-22B, Tiger200K, and LongCat-Video's dataset pipelines. Expect **$0.001–0.003 per minute** of reference video on a rented L4.

**Shot classification.** There is no dominant off-the-shelf cinematography classifier in 2026. Practical winner: **zero-shot Gemini 2.5 Flash with a strict `responseSchema`** — it ingests an entire shot (few frames at `media_resolution=low`) and returns `{shot_size, motion, subject_type, lighting, dominant_color, camera_move}` in one call. Self-hosted alternative: **Qwen2.5-VL-7B** gives ≥1-hour video understanding with stable JSON output. Skip pure CLIP/SigLIP shot classifiers unless you need sub-ms latency at millions of shots.

**Semantic search for clip↔slot matching.** Use **Twelve Labs Marengo 3** (GA 2026, migrated from 2.7 in March 2026). It's 512-dim, native multimodal (video + audio + image + text in one space), supports 500-token text queries, handles up to 4 hours per asset. Pricing (confirmed April 2026):

| Item | Price |
|---|---|
| Marengo video indexing (one-time) | **$0.042 / min** |
| Storage | $0.0015 / min / month |
| Search API | $4 / 1,000 queries |
| Embed-only (no index) | $0.042/min video, $0.0083/min audio, $0.10/1k images, $0.07/1k text |

The turnkey convenience matters: Marengo captures cinematography terms like "zoom, pan, tracking" natively, which partially subsumes shot-type and motion scoring. Self-hosted **SigLIP-2 keyframe embeddings + Qdrant HNSW** is ~50× cheaper at scale but you lose the audio/speech modality.

**Claude and video.** As of April 2026, **Claude does not natively accept video** — Opus 4.7 and Sonnet 4.6 process text + images only (Opus 4.7 at 4,784 tokens/image, up to 3.75 MP). There's an open GitHub feature request but no shipped capability. This is why Claude sits in the reasoning layer: we feed it *text descriptions* of the reference (Gemini-generated style sheet + allin1 beat map + shot metadata) plus a small bundle of representative keyframes.

**Recommended per-minute budget for the understanding layer:** $0.06–$0.08/min on the quality tier (TransNet V2 self-hosted + Gemini 2.5 Pro style analysis cached + Marengo embeddings + Claude re-rank), dropping to $0.008–$0.012/min on a budget tier (all-Google: Gemini 2.5 Flash + self-hosted SigLIP-2 + Batch API's 50% discount).

## 2. Beat detection and audio analysis

**Primary:** **allin1 (Taejun Kim, WASPAA 2023)** — the only OSS library that emits beats + downbeats + BPM + labeled functional sections (intro/verse/prechorus/chorus/bridge/drop/outro) in one call. Returns an `AnalysisResult` with `bpm`, `beats[]`, `downbeats[]`, `beat_positions[]`, `segments[{start, end, label}]`. SOTA on Harmonix (~89 F1). Demucs demixing is auto-applied; cache `./demix` and `./spec` per song.

**Cross-check / fallback:** **Beat This!** (Foscarin/Schlüter/Widmer, ISMIR 2024, CPJKU/beat_this). Generalization SOTA for beats and downbeats, no madmom dependency (so Python 3.11/3.12 clean). Run it as a consistency check on allin1's beat grid for modern pop/EDM with sidechain compression where allin1 sometimes drifts.

**Energy:** `librosa.feature.rms(y, hop_length=512)` smoothed with a 200 ms Gaussian. **Don't replace allin1 beats with librosa beats — librosa is systematically 20–60 ms late** vs RNN trackers, which breaks beat-aligned cuts.

**Cut-strength strategy** (this is what makes the edit feel good): every cut snaps to the nearest **beat**; every 4–8 cuts force a longer shot at the nearest **downbeat**; dramatic transitions (cross-dissolve, big whip-pan, flash) are reserved for the nearest **segment boundary** where `label` changes (verse→chorus, build→drop).

**Gotchas that will bite you:** madmom's build breaks on Python ≥3.11 (CPJKU issues #527, #535) — isolate any stack that depends on it (allin1's DBN post-processing, BeatNet, Beat Transformer) in a Py 3.9 container, or skip it with Beat This!. MP3 decoders drift 20–40 ms — **always decode to WAV 44.1 kHz PCM via ffmpeg before any tracker**. Skip BEAST (2024) — it's online-streaming-optimized and its offline downbeat F1 (~53) is much worse than allin1 or Beat This!.

## 3. Style extraction from the reference

**LUT / color grade.** Sample 30–100 frames evenly across the reference (skip the first/last 0.5 s and any dark fades). Fit a color mapping with **color-matcher** using the `hm-mvgd-hm` compound method (Hahne's IEEE paper — beats Reinhard, MKL, Pitié, and per-channel histogram matching). Apply the fit to a 33×33×33 identity cube and write as an Iridas `.cube` via `colour-science` (`colour.LUT3D` + `colour.write_LUT`). Apply in FFmpeg with `lut3d=file=style.cube`. Wrap with `zscale=transfer=709` if your source isn't already in Rec.709. **Use 33-point cubes** — 17-point bands on skies. Fallback for stylized looks (hard crushed blacks, split-toning): append a hand-fit 1D tone curve in Rec.709 space.

**Text overlay OCR.** Hybrid: run **PaddleOCR (PP-OCRv4/v5)** at 5–10 FPS for per-frame detection + quadrilateral boxes. Dedupe across frames with IoU ≥ 0.5 and fuzzy string match to produce `(text, start_frame, end_frame, bbox_trajectory)`. Then crop the shot and send to **Gemini 2.5 Pro** with `video_metadata.fps: 10` demanding JSON `{text, font_family_guess, weight, color_hex, stroke, animation_type: fade|slide|typewriter|scale|pop|word_by_word, in_timing, out_timing}`. PaddleOCR handles stylized scene text far better than Tesseract/EasyOCR; Gemini handles *kinetic* typography PaddleOCR misses.

**Transition typing.** TransNet V2's two heads give you cut-vs-gradual probability for free. Classify further: boundary span = 1 frame → **hard cut**. Span > 1 with smooth SSIM decay + monotonic luminance → **dissolve/fade**. Span with structured translating half-plane in `cv2.absdiff` (fit a line to the changed mask over consecutive frames, R² > 0.9) → **wipe** (direction = normal of the line). Span 3–10 frames AND mean |RAFT flow| > 50 px/frame AND Laplacian-variance drop (motion blur) → **whip-pan**. Lower TransNet threshold from 0.5 to 0.3 for music-video content.

**Effects detection.** Fit a 6-parameter affine `cv2.estimateAffinePartial2D` to RANSAC'd LK tracks per frame → `(tx, ty, scale, θ)`. Aggregates per shot give you: static tripod (all near zero), handheld static (high-freq jitter std > 2 px on 1080p), pan (monotonic tx ≫ ty), tilt (ty ≫ tx), zoom (divergence large, scale deviates from 1), dolly/gimbal (all large, oscillating). **Speed ramp** is the tricky one — detect as divergence between (a) per-frame flow magnitude and (b) expected scene-motion prior, cross-checked against audio onset density when diegetic audio exists. **Freeze frame** = mean flow ≈ 0 for ≥4 frames with audio still playing and `cv2.PSNR(prev, cur) > 45 dB`. RAFT OOMs a 12 GB GPU at 1080p — downsample to 720p or use SEA-RAFT (2–3× faster).

**Critical camera-motion gotcha:** a tracking shot with a moving subject looks like a zoom if the subject fills frame. Always fit affine on **background** inliers — RANSAC does this, or mask by a person segmenter first.

## 4. Cut-list generation with Claude

**Model choice:** **Claude Sonnet 4.6** with 1M context at standard pricing ($3/$15 per MTok), extended thinking budget of 2–4K tokens. Use Opus 4.7 only if eval shows a measurable quality lift.

**Reliability pattern (most important decision):** define the cut-list as a tool `input_schema` and call with `tool_choice: {"type": "tool", "name": "emit_cutlist"}`. This is Anthropic's official recommended path for strict JSON and is 10× more reliable than prefill-with-`{` or relying on prose JSON. Wrap with a JSON-schema validator that re-prompts with the validation error on failure — expect <1% retry rate on Sonnet 4.6.

**Prompt caching (essential for unit economics):** cache the system prompt + cut-list schema + any long reference-video analysis (can easily be 20–50K tokens). 5-minute cache write is 1.25× base input; cache reads are **0.1× base input (90% off)**. Combined with Batch API's 50% off for non-interactive runs, you can reach ~95% savings on repeated cut-list iterations over the same reference.

**Cut-list JSON schema** (the contract between analysis and render — version this carefully):

```json
{
  "globals": {
    "total_duration_s": 30.0,
    "tempo_bpm": 120,
    "time_signature": "4/4",
    "key": "F# minor",
    "energy_curve": [0.3,0.35,0.4,0.5,0.7,0.9,0.95,0.9,0.6,0.4],
    "section_markers": [
      {"name":"intro","start_s":0,"end_s":6},
      {"name":"verse","start_s":6,"end_s":14},
      {"name":"prechorus","start_s":14,"end_s":18},
      {"name":"drop","start_s":18,"end_s":26},
      {"name":"outro","start_s":26,"end_s":30}
    ],
    "color_grade_ref": "teal_orange_contrast_1.2",
    "aspect_ratio": "9:16"
  },
  "slots": [
    {"index":0,"start_s":0.0,"duration_s":2.0,"beat_index":0,"section":"intro",
     "transition_in":"fade","transition_out":"hard_cut",
     "target_shot_type":"wide","subject_hint":"establishing location, golden hour",
     "motion_hint":"slow_push","energy_level":0.3,
     "required_tags":["exterior","landscape"],"avoid_tags":["faces","text"]},
    {"index":12,"start_s":18.0,"duration_s":0.8,"beat_index":36,"section":"drop",
     "transition_in":"flash","transition_out":"hard_cut",
     "target_shot_type":"close_up","subject_hint":"high-energy action",
     "motion_hint":"whip","energy_level":0.95,
     "required_tags":["action","fast_motion"]}
  ],
  "overlays": [
    {"text":"CITY NIGHTS","start_s":1.0,"end_s":5.0,
     "position":"center","font":"Inter Black","font_size_px":120,
     "color":"#FFFFFF","stroke":"#000000","animation":"word_by_word"}
  ]
}
```

Enums (`transition_in/out`, `target_shot_type`, `motion_hint`, overlay `position`/`animation`) are essential — free-form strings make the downstream FFmpeg compiler brittle. `beat_index` lets the renderer snap any per-Claude timing drift back onto the actual beat grid.

## 5. Clip matching and ranking

Given the cut-list, rank user clips per slot with a weighted score over five components plus a diversity penalty:

```
Score(s,c) = 0.40·E(s,c)        // Marengo cosine sim(slot prompt, clip embed)
           + 0.20·T(s,c)        // shot-type classifier softmax for target shot
           + 0.15·A(c)          // 0.6·LAION_aesthetic + 0.4·MUSIQ
           + 0.15·M(s,c)        // 1 − |motion_score(c) − energy_s|
           + 0.10·D(s,c)        // exp(−((|dur(c)−dur(s)|)/dur(s))²/0.5)
           − 0.25·R(c,chosen)   // max cosine to any already-chosen clip
```

**Component sources.** `E` is Marengo 3 text-embed of the slot's `subject_hint + motion_hint + target_shot_type + required_tags` against Marengo video-embeds per clip segment. `T` is a fine-tuned ViT/CLIP shot-type classifier (train on MovieShots + ShotType). `A` is LAION aesthetic predictor v2 on CLIP ViT-L/14 embeddings, combined with MUSIQ for technical quality; average over 3–5 sampled frames per clip, penalize the worst frame. `M` comes from RAFT flow magnitude normalized + categorical `motion_hint` overlap. `D` is a Gaussian centered on duration fit.

**Diversity.** Greedy MMR over slots in order; after picking slot *s*, penalize remaining candidates by cosine similarity to already-chosen embeddings. Hard constraints: no clip used twice in a window <6 s, no same face-cluster in adjacent slots unless `subject_hint` demands continuity, rotate shot-types except for intentional beat-match sequences. When clip libraries are ≤200, formulate as an assignment problem and solve with Hungarian for a global optimum — otherwise greedy + local swap.

**Semi-auto UI.** Return top-3 per slot. **Confidence** = calibrated sigmoid of (score_top1 − score_top4) × k, clipped [0,1]. Expose the sub-scores in the UI ("Strong semantic match, weak aesthetic") so users understand overrides. Low confidence → prompt user to upload more clips or pick manually.

## 6. Render pipeline

**Primary engine: FFmpeg via subprocess orchestrated from Python, with PyAV for probing and metadata.** No other tool supports `lut3d` + frame-exact cuts + arbitrary `xfade` + custom `drawtext` + specific bitrates in one pipeline. Avoid **MoviePy** on the hot path — known perf issues (GitHub #2165) and no `lut3d` support; keep it for dev tooling only. Skip **Remotion Lambda** because it's CPU-only with no GPU path, no `lut3d`, and 4K costs spike. Skip **Shotstack** and **Creatomate** — fixed vendor JSON, no LUTs, no frame-level control.

**Per-operation recipes.**

*Frame-accurate cuts:* `-ss` before `-i` is keyframe-aligned (fast but inaccurate); `-ss` after `-i` is frame-exact but slow. For beat-aligned cuts, always re-encode with `trim=start_frame=X:end_frame=Y,setpts=PTS-STARTPTS` on the filter graph. PyAV gives you exact PTS via `stream.time_base`.

*Transitions:* `xfade` has 50+ built-ins — `fade`, `wipeleft/right/up/down`, `circleopen`, `slideup`, `pixelize`, `hlslice` for whip-pan approximations. Chain: `[0][1]xfade=transition=fade:duration=0.5:offset=5`.

*LUT:* `-vf zscale=transfer=709:range=tv:out_range=pc,lut3d=/path/style.cube,zscale=range=pc:out_range=tv`. Order matters — LUT after decode, before scale/encode.

*Text:* `drawtext=fontfile=/fonts/Inter.ttf:text='...':x='if(lt(t,1),w-w*t,0)':y=H-50:fontsize=48` for animated slide-ins. For complex kinetic typography, pre-render a PNG sequence in Python (Pillow/Skia) and overlay with `overlay=x=X:y=Y`.

*Final encode (720p master):* `-c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart`. Drop to `-crf 20 -preset medium` if you blow the 2–3 min budget. On a GPU worker: `-c:v h264_nvenc -preset p6 -rc vbr -cq 19`.

**Upscaling.** Render 720p master, upscale on demand — saves 4× compute per render. MVP default: **Real-ESRGAN-ncnn-vulkan** on a Modal L4 ($0.000222/s), roughly **$0.05–0.15 per minute** for 1080p→4K. Pro tier: **Topaz Video AI API** (GA late 2025, Precision Update March 2026 with Gaia 2 and Starlight Precise 2.5), **$0.42–1.00 per video** passed through as an upsell. Skip **VideoGigaGAN** — Adobe has not released weights; the popular GitHub repo is an unofficial `lucidrains` reimplementation with no pretrained checkpoints.

## 7. Infrastructure and architecture

**Monorepo layout.** pnpm workspaces + Turborepo (JS/TS) and uv workspaces (Python) coexist in one git repo — they don't touch each other's artifacts.

```
repo/
├── package.json, pnpm-workspace.yaml, turbo.json
├── pyproject.toml (uv workspace root), uv.lock
├── apps/
│   ├── web/         # Next.js 15 + React 19 + Tailwind + shadcn/ui
│   └── api/         # Node 22 + Fastify 5 + TypeScript + Zod + @clerk/fastify
├── packages/        # shared JS/TS: ui, shared-types, timeline-spec, eslint-config
├── services/        # Python workers (uv members)
│   ├── ingest-worker/    # probe, shot detect, beat detect, OCR
│   ├── style-worker/     # LUT extraction, transition typing, effects
│   ├── reason-worker/    # Claude cut-list generation + clip ranking
│   ├── render-worker/    # ffmpeg/PyAV primary render
│   ├── upscale-worker/   # Real-ESRGAN / Topaz client
│   └── shared-py/
├── infra/docker, infra/modal, infra/terraform
```

**Orchestration.** **Temporal Cloud** (~$100/mo starter) with Python SDK for workers and TypeScript SDK for the API. One `VideoRenderWorkflow` with activities `probe_inputs` → `detect_beats` → `detect_shots` → `analyze_reference_style` → `embed_user_clips` → `generate_cutlist_claude` → `rank_clips_per_slot` → `build_timeline` → `render_720p` → `apply_lut` → `burn_text` → `maybe_upscale` → `upload_to_r2` → `notify_user`. Each activity gets its own retry/timeout policy. Progress flows via Temporal signals → Redis pub/sub → SSE to browser. **Descript uses Temporal v1.26 for AI video processing at scale — same workload shape.** Skip BullMQ/Celery (no durable workflows), AWS Step Functions (lock-in, painful JSON DSL), Inngest (smaller ecosystem, SaaS-first).

**Storage.** **Cloudflare R2** for uploads and renders: $0.015/GB-month, **$0 egress**, 10 GB + 1M Class A + 10M Class B ops free per month. At 1 TB stored and 10 TB delivered/month that's ~$15 vs ~$900+ on S3 Standard. Put **Cloudflare CDN in front** for true zero egress — CloudFront in front of R2 still charges CloudFront egress. Gotcha: Uppy + R2 multipart requires `ETag` in the CORS `ExposeHeaders` or completion fails.

**Uploads.** **Uppy v4 + `@uppy/aws-s3` plugin → R2 multipart** via presigned URLs from the Node API. 10–50 MB parts, 15-min presign re-issue via `onBeforeRequest`, lifecycle rule to abort incomplete multipart uploads after 24 h. Skip tusd — R2 multipart gives you resume already.

**GPU.** Needed for TransNet V2, Real-ESRGAN, optional local MLLM calls. **Modal** as primary: sub-second cold starts (often <1 s on Rust containers), per-second billing — L4 $0.80/hr, A10G $1.10/hr, L40S $1.95/hr, A100 40GB $2.10/hr, H100 $3.95/hr. Python-native decorators, scale-to-zero. **Rule of thumb:** utilization <40% → Modal; sustained ≥40% → switch that workload to a **RunPod Pod** (~40–60% cheaper) or Lambda Labs VM. Modal GPUs are all preemptible, so checkpoint long Real-ESRGAN jobs every N frames — Temporal retries make this trivial.

**Real-time progress.** **SSE** from the Node API (`GET /api/jobs/{id}/events`) subscribed to a Redis pub/sub channel keyed by job id. Workers `PUBLISH job:{id} {stage, progress}` every 1–2 s. Auto-reconnect, HTTP/2-friendly, proxy-compatible. Skip WebSockets unless you later add collaborative editing.

**Auth.** **Clerk**. Free to 10k MAU, $0.02/MAU beyond, pre-built `<SignIn/>` `<UserProfile/>` components, integrates in <1 day. Pass the verified Clerk JWT as a Temporal workflow input for audit trails. Runner-ups: Supabase Auth if you're using Supabase anyway; Auth0 only for enterprise SAML on day one.

## 8. UX flow

**Project creation.** User logs in (Clerk), creates a project, names it. One screen, three uploaders.

**Upload step.** Uppy presents three dropzones: "Reference video" (≤5 min, MP4/MOV, shows a thumbnail on complete), "Your clips" (multi-select, no limit but warn >30 clips), "Your song" (audio file). R2 multipart uploads proceed in the background while the user picks style tier. A progress bar per asset plus an overall project readiness indicator.

**Style tier selection.** Four radio cards, each with a small preview strip showing what's added:
1. **Cut timing only** — Beat-synced cuts and basic transitions from the reference. Fastest, ~1–2 min render.
2. **+ Color grade** — Adds the reference's LUT applied to your clips. ~2–3 min render.
3. **+ Text overlays** — Adds reference's title cards/kinetic captions (you can edit the copy). ~2–3 min render.
4. **Full style transfer** — Effects (zoom, shake, speed ramps), camera-motion emulation, transitions, overlays, LUT. ~3–4 min render.

Mode toggle at the top: **Auto** (fully automated) vs **Assisted** (review each slot).

**Analysis phase (streaming, ~30–60 s).** Real-time status via SSE: "Detecting shots (23/48)", "Extracting beat grid", "Analyzing color grade", "Parsing text overlays". A side panel shows the reference parsed into a beat-aligned timeline with shot-type labels and section markers — this alone is a "wow" moment and demonstrates we understand their reference.

**Cut-list review (Assisted mode only).** The generated cut-list appears as a horizontal timeline with one card per slot. Each card shows: slot duration, target shot type icon, energy bar, transition icons on each end, top-3 ranked clip thumbnails with confidence bars and sub-score chips ("semantic 0.82 · shot 0.91 · aesthetic 0.64"). User clicks a thumbnail to select or "Show more" to expand to top-10. Keyboard shortcuts (arrow keys + enter) for fast review. A "Use auto picks" button accepts all top-1 choices.

**Preview.** Before final render, generate a **360p proxy preview** using only the first slot-to-slot selections and a fast `-preset ultrafast -crf 28` pass (~15–20 s). User plays it inline. Accept → kick off full render. Reject → back to cut-list review.

**Render phase.** Temporal workflow runs; SSE streams stages ("Rendering 720p master, frame 840/1800"). User can leave and come back — progress is durable.

**Delivery.** R2 signed URL behind Cloudflare. Download button for 720p, optional "Upscale to 1080p/4K" button triggers the upscale workflow as a secondary job. Share link (signed, 7-day expiry) for showing clients.

## 9. Cost model per 60-second final output

Assumes a 90-second reference, 5 user clips averaging 30 s each (150 s of user footage), the quality tier stack, and a 60-second output at 720p with LUT + text overlays.

| Item | Quantity | Unit cost | Subtotal |
|---|---|---|---|
| TransNet V2 shot detection (ref + clips = ~4 min) | 4 min | $0.003/min (L4) | $0.012 |
| Gemini 2.5 Pro reference style analysis (cached after first call) | ~1.5 min equivalent tokens | $0.0194/min first / 90% off cached | $0.029 first, $0.003 cached |
| Gemini 2.5 Flash per-shot classification on user clips | ~40 shots × 2s | $0.0046/min × 1.5 min | $0.007 |
| Twelve Labs Marengo 3 indexing (ref + user clips) | ~4 min | $0.042/min | $0.168 |
| Marengo storage (one project-month) | 4 min × 1 mo | $0.0015/min/mo | $0.006 |
| Marengo search queries (~20 for cut-list + ranking) | 20 | $4/1k | $0.080 |
| Claude Sonnet 4.6 cut-list generation (extended thinking, cached system prompt) | ~8k in cached + 3k in fresh + 4k out | cache read $0.3/MTok, input $3, output $15 | $0.074 |
| PaddleOCR on reference (CPU, negligible) | 1.5 min | $0.0005/min | $0.001 |
| color-matcher LUT fit (CPU, negligible) | 1 run | ~$0.0001 | $0.000 |
| FFmpeg render 720p (libx264 preset slow, CPU on Modal) | ~90 s compute | $0.000057/s (8-core) | $0.005 |
| R2 storage (project + output, 1 mo) | ~500 MB × 1 mo | $0.015/GB-mo | $0.008 |
| R2 + Cloudflare egress (CDN delivery) | 200 MB | $0 | $0.000 |
| **Subtotal — cold render (first user on this reference)** | | | **~$0.39** |
| **Subtotal — warm render (reference cached)** | | | **~$0.36** |
| Optional Real-ESRGAN upscale 720p→4K | 60 s | ~$0.10/min | $0.10 |
| Optional Topaz Video AI API upscale (Pro tier) | 1 video | pass-through | $0.42–1.00 |
| **All-in with Real-ESRGAN 4K upscale** | | | **~$0.46** |
| **All-in with Topaz 4K upscale** | | | **$0.78–1.36** |

At scale — 10,000 renders/month — that's **$3,900–$4,600/mo COGS** on the core pipeline plus $4,600–$13,600/mo if 100% choose Topaz. Gross margin at a $9.99/render or $29/mo subscription is comfortably above 80%. Dominant cost centers are Twelve Labs indexing ($0.17/render, 40% of base), Claude cut-list ($0.07, 19%), and Marengo search ($0.08, 22%). **Biggest lever: self-host SigLIP-2 embeddings + Qdrant once you have scale** — drops Twelve Labs from $0.25/render to ~$0.01, cutting COGS in half.

## 10. MVP module breakdown and phased build order

**Phase 0 — Scaffolding (Week 1).** Monorepo with pnpm/Turbo + uv workspaces. Clerk auth integrated on `apps/web` and `apps/api`. Temporal Cloud account + hello-workflow running. R2 buckets with CORS. Uppy multipart upload → R2 working end-to-end with a dummy job. Modal account with one GPU function running as sanity check. Neon Postgres + Prisma (or Drizzle) schema: `users, projects, assets, renders, cut_lists`. Qdrant Cloud instance provisioned.

**Phase 1 — "It renders something" skeleton (Week 2).** `ingest-worker`: ffmpeg probe, PySceneDetect shot boundaries (TransNet V2 can slot in later), allin1 beat/downbeat/section detection. `render-worker`: FFmpeg + PyAV timeline compiler that takes a **hard-coded cut-list JSON** and renders a 720p MP4 — no style transfer yet, just beat-snapped cuts from the user's clips in order with hard cuts between them. Celebrate: you have a video editor.

**Phase 2 — Claude cut-list + clip ranking (Week 3–4).** `reason-worker`: Claude Sonnet 4.6 with tool-forced JSON emitting the cut-list schema above. Cached system prompt. Marengo indexing for user clips and reference. Slot-ranking service with the weighted scoring formula. Fully automated end-to-end flow: upload → analyze → generate cut-list → auto-pick top-1 per slot → render. This is your demo.

**Phase 3 — Tier 1 "cut timing + transitions" (Week 5).** TransNet V2 shot-boundary detection on the reference (replacing PySceneDetect). Transition classifier (cut / dissolve / wipe / whip-pan) via TransNet gradual prob + flow + mask geometry. FFmpeg `xfade` transitions applied per cut-list. Ship the fully-auto mode to friendly users.

**Phase 4 — Tier 2 "color grade" (Week 6).** `style-worker`: color-matcher LUT extraction → `.cube` file → stored in R2 alongside the project. Render worker adds `lut3d` to the filter chain. Ship as a tier option.

**Phase 5 — Tier 3 "text overlays" (Week 7).** PaddleOCR per-frame → dedupe/track → Gemini 2.5 Pro for font/color/animation extraction. Render worker composites pre-rendered PNG sequences or uses `drawtext`. User can edit the detected copy before render.

**Phase 6 — Assisted (semi-auto) mode UI (Week 8–9).** Cut-list review timeline with top-3 per slot, confidence bars, keyboard nav, sub-score chips. 360p proxy preview before final render. This is the quality tier that will differentiate vs. pure-auto competitors.

**Phase 7 — Tier 4 "effects + camera motion" (Week 10–11).** Flow-based zoom/shake/ramp/freeze detection. Apply approximations in FFmpeg (`zoompan`, `vidstab` for shake, `setpts` for speed ramps, `tpad` for freezes). This is the hardest tier to get right — many effects will look wrong without matching the reference's *intent*; limit to high-confidence matches.

**Phase 8 — Upscale pathway and polish (Week 12+).** Real-ESRGAN upscale worker on Modal L4. Topaz API integration as Pro tier. Signed share links, project history, render versioning, basic analytics.

## 11. Risks and mitigations

**Clip-to-slot mismatch** is the biggest product risk. Users will upload a pile of vacation footage and expect a coherent edit; if slot 3 demands a "close-up, high-energy action shot" and their library has only wide landscapes, rankings will all be weak. **Mitigations:** (a) before generating the cut-list, analyze the user clip library and *constrain the cut-list schema* to shot types the library can plausibly fill — pass available shot-type histogram to Claude as context. (b) Add an explicit "your library is mostly wide shots; the generated edit will favor environmental pacing" pre-flight message. (c) In semi-auto mode, flag low-confidence slots with an amber badge and offer "upload more" or "re-roll this slot."

**Awkward beat-sync** — cuts feel mechanical or off. **Mitigations:** (a) never snap every cut to every beat — use the downbeat-escalation rule (every 4–8 cuts land on a downbeat, section-boundary cuts get transitions). (b) Reserve beat-1 of the chorus/drop for the highest-energy clip; don't start a new clip *mid-word* in vocals (use allin1's `beat_positions` to detect vocal onsets and nudge cuts off them). (c) Add a ±20 ms random jitter budget to avoid metronomic feel.

**Ugly LUT transfer.** Color-matcher can over-saturate on teal-and-orange grades or crush blacks. **Mitigations:** (a) sample exclusion — remove letterboxed bars, subtitles, near-black/near-white frames from the fit set. (b) Always apply the LUT at 30–70% strength by default (`lut3d=...:interp=tetrahedral` with a pre-mix), let users nudge. (c) Compare the LUT-applied user frame vs. original with SSIM; if SSIM < 0.4, the LUT is likely broken — fall back to Reinhard transfer or alert the user.

**Long render queues under load.** 2–3 min per render times 500 concurrent users → users abandon. **Mitigations:** (a) Temporal's work queue + Modal's autoscaling scale to demand; set worker min/max bounds. (b) Pre-render the 360p proxy fast (15–20 s) so users see *something* while the full render queues. (c) Publish expected wait time via SSE based on queue depth. (d) Soft-limit free-tier concurrency to 1 render per user.

**Twelve Labs vendor lock-in / pricing shifts.** Marengo 2.7 → 3.0 forced re-indexing in March 2026 — if 4.0 does the same mid-launch, it's painful. **Mitigations:** (a) abstract the embedding layer behind an `EmbeddingProvider` interface from day one (`embed(clip) -> vector`, `search(query_embed, filter) -> hits`). (b) run SigLIP-2 self-hosted as a shadow/fallback even on the premium tier, storing both embeddings.

**Madmom / Python packaging hell.** allin1 and Beat Transformer both pull madmom, which is broken on Python ≥3.11 without Cython patches. **Mitigations:** (a) isolate audio workers in a Python 3.9 container dedicated to beat tracking; all other workers run Python 3.12. (b) Eval Beat This! as a drop-in replacement path — it has no madmom dependency.

**Claude JSON validity.** Even with tool-forced output, occasional invalid JSON happens. **Mitigations:** (a) server-side schema validator with detailed error → re-prompt with error message (Anthropic's documented pattern). (b) cap retries at 3; if still invalid, fall back to Opus 4.7. (c) emit the cut-list in chunks (first globals, then slots) when thinking budget is tight.

**Hallucinated overlays or effects.** Gemini sometimes invents overlay text or animation types. **Mitigations:** (a) separate the "exact quoted text" extraction (PaddleOCR, deterministic) from the "style description" (Gemini). (b) reconcile: Gemini suggestions must have a PaddleOCR bbox to be included; otherwise drop.

**Copyright on reference videos.** Users will upload copyrighted TikToks/music-videos as references. We only *extract style features* (beat grid, shot timing, LUT, transition sequences) — none of those are copyrightable on their own (cf. "styles cannot be copyrighted" Warhol/Goldsmith scope). **Mitigations:** (a) ToS explicitly states reference videos are analyzed only for abstract style features, not stored beyond the project session, and never redistributed. (b) Automatically delete reference video bytes from R2 after 24 h; retain only the extracted feature JSON.

**Song copyright.** A user uploading a copyrighted song and downloading a final edit could create DMCA exposure. **Mitigations:** (a) ToS requires user to own or license the song. (b) integrate a royalty-free music library tier (Epidemic Sound, Artlist API) as a safe default. (c) add Content ID-style fingerprinting later.

## 12. Competitive positioning

The AI video tool market as of April 2026 splits cleanly into two camps, and **reference-style matching sits between them in an unoccupied niche**.

*Highlight extractors* (Opus Clip, Captions.ai, Submagic, Vizard, AutoPod, Descript, Wisecut) pull clips and captions *from within* the user's existing footage. None of them take an external reference. Opus Clip had a ~48 h outage in February 2026 that pushed creators to try alternatives — a signal that product reliability and differentiation matter more than ever. Submagic and Captions remain caption-layer-strong but don't restructure video.

*Generative video tools* (Runway Gen-4/4.5, Pika 2.2, Kling 3.0, Luma Ray2, Kaiber) make new pixels. Runway's "camera motion reference" (April 2026) uses a reference video only to guide the motion of a *newly generated* clip — closest conceptual cousin, but it doesn't re-edit user footage. Adobe's Firefly Quick Cut (February 2026) assembles a first cut from user clips, but it's driven by a **text description**, not a video reference. Firefly's new AI Assistant (April 16, 2026, beta) hints that Adobe is converging on agentic editing across Premiere/Photoshop/Firefly — they'll eventually ship reference-video matching, which is a real competitive threat on a 12–18 month horizon.

*Template platforms* (CapCut AI templates, InShot, VN) offer beat-synced templates users drop footage into — but templates are authored by humans, not parsed from arbitrary references. When a creator wants to emulate a specific music video or TikTok aesthetic that no template captures, they're stuck.

**The wedge:** parse a reference's cut rhythm, shot-type sequence, color grade, transitions, and overlays → map onto the user's clip library → sync to a custom song. **No one ships this today.** The defensibility comes from (a) the reference-parsing pipeline (shot + beat + style + OCR fused into a structured representation), (b) the cut-list schema as a stable contract, and (c) the clip-ranking logic tuned over time. Marengo 3's cinematography-aware embeddings make the ranking side quickly credible; Claude's structured reasoning makes the cut-list side quickly credible; the combination is not trivial to replicate.

**Go-to-market angle.** Lead with "recreate this TikTok/music-video's edit style with your own footage." TikTok-native creators copying viral edit styles is the wedge audience. The second wave is marketers/brands who want to emulate a competitor's or benchmark brand's style in a campaign video. Price the MVP at $0 for 3 renders/month, $19/mo for 30 renders with 720p, $49/mo for unlimited + 4K Real-ESRGAN upscale, $99/mo for Topaz Starlight upscale and priority queue.

## Bottom line

The stack is opinionated, buildable, and cost-viable. A senior SRE who can write Python and TypeScript can ship the end-to-end demo in 4 weeks (Phase 0–2), ship the fully-auto with all four tiers in 10–12 weeks (through Phase 7), and hit sub-$1 unit cost from day one. The one technical bet that matters more than any other is the **cut-list JSON schema as a hardened contract** between the analysis side (Gemini + Twelve Labs + classical CV) and the render side (FFmpeg) — version it, validate it, and everything else can be swapped (Claude → GPT → open model; Marengo → SigLIP-2 self-hosted; Real-ESRGAN → Topaz) without touching the render compiler. That abstraction is what lets you ride out the next 18 months of model releases while Adobe inevitably tries to build what you're building.