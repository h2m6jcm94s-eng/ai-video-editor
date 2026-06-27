# Glossary & References

## A

**Activity (Temporal)**
A single unit of work in a Temporal workflow, e.g. `compile_render` in `services/render-worker/src/render_worker/activities.py`. Activities can retry independently and are where side effects (FFmpeg, HTTP, file I/O) happen.

**AnalyzeGenomeWorkflow**
Temporal workflow defined in `services/style-worker/src/style_worker/workflows.py` that extracts a 50-feature Style Genome from a reference video.

**AnalyzeStyleWorkflow**
Temporal workflow that runs LUT extraction, transition classification, camera motion analysis, and text overlay detection in parallel.

**Anticipation offset**
A small shift applied to a clip's source window so that a cut lands on a beat while the visual action still reads clearly. See `services/reason-worker/src/reason_worker/anticipation.py`.

## B

**Batch2 offline render**
Standalone CLI pipeline at `scripts/batch2-offline-render.py` that runs the full AI editing pipeline without API/Temporal.

**BeatGrid**
Shared model (`services/shared-py/src/shared_py/models.py`) representing BPM, beat times, downbeats, and section markers for a song.

## C

**Clip ranking**
Scoring every user clip for each cutlist slot using weighted features. See `services/reason-worker/src/reason_worker/clip_rank.py`.

**Cutlist**
The structured editing timeline: globals + slots + overlays + subtitles + audio tracks. Defined in `packages/shared-types/src/schemas.ts` and `services/shared-py/src/shared_py/models.py`.

## D

**DBSCAN**
Density-based clustering used to group face embeddings into identities. See `services/shared-py/src/shared_py/identity_cluster.py`.

**Dialogue bus**
A mixed, gated, and compressed audio track of all dialogue extracts used as the sidechain key for music ducking. Built in `services/render-worker/src/render_worker/compiler.py`.

## E

**Effect**
A timed visual or audio transformation (zoom, shake, text, SFX, etc.). Schemas in `packages/shared-types/src/effects.ts` and `services/shared-py/src/shared_py/models.py`.

**Export preset**
A named output dimension preset (`reels_9_16`, `youtube_16_9`, `square_1_1`, `auto`). Stored on the render row and used by `compile_render`.

## F

**FaceDetection**
Dataclass in `services/ingest-worker/src/ingest_worker/identity.py` representing one detected face with bbox, embedding, confidence, and face-area ratio.

**FFmpeg filter_complex**
The directed acyclic graph of FFmpeg filters that composes segments, transitions, overlays, and audio. Built in `services/render-worker/src/render_worker/compiler.py`.

## G

## H

**Heatmap**
Per-clip sliding-window quality scores used to pick the best source window for each slot. See `services/ingest-worker/src/ingest_worker/heatmap.py`.

**HWAccel / CUDA decode**
Experimental FFmpeg hardware decode enabled with `AVE_USE_HWACCEL=1`. See `_extract_segment` in `services/render-worker/src/render_worker/compiler.py`.

## I

**Identity**
A cluster of face detections representing one recurring subject. Defined in `services/shared-py/src/shared_py/identity_cluster.py`.

**InsightFace**
Face detection/recognition library used to extract face embeddings. Loaded lazily in `services/ingest-worker/src/ingest_worker/identity.py`.

## J

## K

**Kinetic text**
Animated text that can be composited behind a masked subject. See `_render_layered_text` in `services/render-worker/src/render_worker/compiler.py`.

## L

**LUT (Look-Up Table)**
A `.cube` file extracted from the reference video for color matching. See `services/style-worker/src/style_worker/lut_extract.py`.

## M

**Mask**
A black-and-white or alpha video that isolates a subject. SAM3 generates masks; the render worker composites them.

**Momentum scoring**
Optical-flow-based coherence score that rewards clip sequences whose motion directions match. See `services/reason-worker/src/reason_worker/momentum.py`.

## N

**NVENC**
NVIDIA hardware video encoder (`h264_nvenc`). Auto-enabled in the render compiler when available.

## O

**Orchestrator**
Standalone Python CLI at `services/orchestrator.py` that runs the pipeline without Temporal.

## P

**Protagonist**
A top-ranked identity by screen time, used to drive subject masks and layered text. Selected in `services/reason-worker/src/reason_worker/protagonist_pick.py`.

## Q

**Quality profile**
One of `preview`, `draft`, `demo`, `export`, `archive`; maps to libx264 preset + CRF. Defined in `services/shared-py/src/shared_py/tuning.py`.

## R

**RankTuning**
Centralized scoring weights in `services/shared-py/src/shared_py/tuning.py`.

**RenderConfig**
Pydantic model in `services/shared-py/src/shared_py/models.py` that carries all compiler settings: dimensions, codecs, quality, masks, audio tracks, and NVENC flags.

## S

**SAM3**
Segment Anything Model 3 (placeholder name used in code) for subject mask generation. See `services/segment-worker/src/segment_worker/engine.py`.

**Shot boundary**
A detected cut point in a video. Models in `services/shared-py/src/shared_py/models.py`, detection in `services/ingest-worker/src/ingest_worker/shot_detect.py`.

**Style Genome**
A 50-feature numeric fingerprint extracted from a reference video. See `services/style-worker/src/style_worker/genome/extract.py`.

**StyleTier**
One of `cuts_only`, `color_grade`, `with_text`, `with_effects`, `full_remix`. Gated in the render compiler.

## T

**Task queue (Temporal)**
Named queue a worker polls. The repo uses `ingest`, `style`, `segment`, and `video-render-queue`.

**Temporal**
Durable workflow orchestrator. Workflow definitions are in each worker's `workflows.py`.

**Transition**
How one slot replaces the next (hard_cut, dissolve, wipe, whip, etc.). Mapped to FFmpeg `xfade` in `services/render-worker/src/render_worker/compiler.py`.

## U

## V

**VideoRenderWorkflow**
The end-to-end render workflow in `services/render-worker/src/render_worker/workflows.py`.

## W

**Workflow (Temporal)**
A durable, retryable sequence of activities. See `services/*/src/*_worker/workflows.py`.

## External libraries & tools

| Tool/Library | Purpose | Where it appears |
|---|---|---|
| FFmpeg | Video/audio decode/encode/filtering | `services/render-worker/src/render_worker/compiler.py` |
| PyAV | Pythonic FFmpeg bindings for probing | `services/ingest-worker/src/ingest_worker/probe.py` |
| librosa | Audio analysis (beats, onset, structure) | `services/ingest-worker/src/ingest_worker/beat_detect.py` |
| PySceneDetect | Shot boundary detection | `services/ingest-worker/src/ingest_worker/shot_detect.py` |
| TransNet V2 | Neural shot detector | `services/ingest-worker/src/ingest_worker/shot_detect.py` |
| InsightFace | Face detection / embeddings | `services/ingest-worker/src/ingest_worker/identity.py` |
| scikit-learn | DBSCAN clustering | `services/shared-py/src/shared_py/identity_cluster.py` |
| PaddleOCR | Text overlay detection | `services/style-worker/src/style_worker/text_detect.py` |
| OpenCV | Optical flow, image I/O | `services/style-worker/src/style_worker/camera_motion.py` |
| Temporal | Workflow orchestration | All `workflows.py` / `__main__.py` |
| Fastify | API backend | `apps/api/src/app.ts` |
| Next.js | Web frontend | `apps/web/src/app/` |
| Drizzle ORM | Database schema/queries | `apps/api/src/db/schema.ts` |
| Clerk | Authentication | `apps/api/src/middleware/auth.ts` |
| MinIO / R2 | Object storage | `apps/api/src/services/storage.ts`, `services/shared-py/src/shared_py/storage.py` |
| Redis | Cache, queue, pub/sub | `apps/api/src/lib/redis.ts` |
