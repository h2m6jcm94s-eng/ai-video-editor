# 01 — Features Overview

This document describes what the AI Video Editor does from a product perspective and maps each capability to the code that implements it.

---

## 1. Core user flow

1. **Upload a reference video** — the style the user wants to match.
2. **Upload clips** — the raw footage to edit.
3. **Upload a song** — the music to sync to.
4. **Pick a style tier** — one of five presets that gate which AI features run.
5. **Hit render** (or prompt-edit the cutlist first).

The system then:

- Probes all media for duration, dimensions, fps, codec.
- Detects beats, shot boundaries, transitions, text, color, motion, faces, and a 50-feature **Style Genome**.
- Ranks clips per slot using weighted scoring, diversity penalties, and optional momentum/anticipation.
- Builds a **cutlist** — a structured timeline with slots, overlays, subtitles, and audio tracks.
- Compiles the final MP4 with FFmpeg, optionally using NVIDIA NVENC and identity-aware subject masks.

Main orchestration code:

- Temporal render workflow: `services/render-worker/src/render_worker/workflows.py`
- Offline CLI that runs the same pipeline: `scripts/batch2-offline-render.py`
- Shared Pydantic models: `services/shared-py/src/shared_py/models.py`

---

## 2. The 5-tier StyleTier ladder

The tier controls how much of the reference analysis is applied to the output.

| Tier | What runs | Code reference |
|---|---|---|
| `cuts_only` | Beat detect + shot detect → programmatic cutlist | `reason_worker/cutlist_gen.py` |
| `color_grade` | + LUT extraction from reference | `style_worker/lut_extract.py` |
| `with_text` | + Text overlay extraction (PaddleOCR) and subtitles | `style_worker/text_detect.py`, `render_worker/compiler.py` |
| `with_effects` | + Transition classifier + camera motion + SFX | `style_worker/transition_type.py`, `style_worker/camera_motion.py` |
| `full_remix` | All above + manual effects, multi-song, prompt edits | `apps/api/src/services/ai.ts`, `render_worker/compiler.py` |

Tier gating is enforced in the render compiler at `services/render-worker/src/render_worker/compiler.py` (`compile_timeline`, `_tier_index`).

---

## 3. Ingest / analysis features

### 3.1 Media probing

Every uploaded asset is probed for:

- duration, width, height, fps, codec, bitrate, color space

Implementation: `services/ingest-worker/src/ingest_worker/probe.py`

### 3.2 Beat detection

The song is analyzed to produce:

- BPM
- Beat positions
- Downbeats
- Energy curve
- Section markers (intro/verse/chorus/drop/outro)

Implementation: `services/ingest-worker/src/ingest_worker/beat_detect.py`

### 3.3 Shot detection

The reference video is split into shots using:

- PySceneDetect content detection
- TransNet V2 neural shot detector (optional)

Implementation: `services/ingest-worker/src/ingest_worker/shot_detect.py`

### 3.4 Heatmap scoring

Each user clip is scored in sliding windows against the song to find the best moments to use. Windows are cached on disk.

Implementation: `services/ingest-worker/src/ingest_worker/heatmap.py`

### 3.5 Style analysis

The reference video is analyzed for:

- Color palette / LUT
- Contrast / saturation / brightness
- Detected transitions
- Camera motions (pan, tilt, zoom, handheld, gimbal)
- Text overlays

Implementation:

- `services/style-worker/src/style_worker/lut_extract.py`
- `services/style-worker/src/style_worker/transition_type.py`
- `services/style-worker/src/style_worker/camera_motion.py`
- `services/style-worker/src/style_worker/text_detect.py`

### 3.6 Style Genome

A 50-feature numeric fingerprint is extracted from the reference. It captures five families of style:

- `cut_rhythm` — cut density, duration stats, transition ratios
- `motion` — motion energy and camera-move percentages
- `dwell` — face size, subject count, screen time
- `audio_align` — cuts aligned to beats, music ducking, dialogue
- `composition` — dominant shot size, rule-of-thirds ratio

Implementation: `services/style-worker/src/style_worker/genome/extract.py`

Models: `services/shared-py/src/shared_py/models.py` (`StyleGenome`, `StyleGenomeFamilies`)

### 3.7 Face detection & identity clustering

- Frames are sampled from selected clips.
- InsightFace extracts face bounding boxes and embeddings.
- Detections are cached as `{clip}.faces.json`.
- DBSCAN clusters faces across clips into recurring **identities**.
- Top identities by screen time become **protagonists**.
- During render, SAM3 generates a subject mask for any slot containing a protagonist.

Implementation:

- Face extraction: `services/ingest-worker/src/ingest_worker/identity.py`
- Clustering / protagonist selection: `services/shared-py/src/shared_py/identity_cluster.py`, `services/reason-worker/src/reason_worker/protagonist_pick.py`
- Mask compositing: `services/render-worker/src/render_worker/identity_matte.py`

---

## 4. Reason / decision features

### 4.1 Cutlist generation

Two paths:

- **AI-driven**: Claude/OpenAI forced tool-use with a JSON schema describing the cutlist.
- **Programmatic fallback**: Beat grid + shot boundaries + energy curve → deterministic cutlist without an LLM.

Implementation:

- `services/reason-worker/src/reason_worker/cutlist_gen.py`
- Fallback ranking model: `services/shared-py/src/shared_py/models.py` (`ClipScore`, `CutList`, `Slot`)

### 4.2 Clip ranking

For each slot, candidate clips are scored on:

- semantic similarity
- shot-type match
- aesthetic quality
- motion energy
- duration fit
- heatmap window quality
- diversity penalty (avoid reusing the same clip)
- repetition penalty (avoid back-to-back reuse)
- momentum coherence (optional optical-flow based)

Implementation: `services/reason-worker/src/reason_worker/clip_rank.py`

Tuning constants: `services/shared-py/src/shared_py/tuning.py` (`RankTuning`)

### 4.3 Anticipation offsets

The ranker can shift a clip's source window start slightly before a dominant motion peak so the cut lands on the beat while the action still reads clearly.

Implementation: `services/reason-worker/src/reason_worker/anticipation.py`

### 4.4 Audio mix

The final audio combines:

- A music bed
- Per-slot dialogue/voiceover tracks extracted from clips
- Adaptive ducking: the music bed is sidechain-compressed by the dialogue bus
- Iconic phrase detection (lyric overlays)

Implementation: `services/reason-worker/src/reason_worker/audio_mix.py`

---

## 5. Render features

### 5.1 Timeline compiler

The render worker:

1. Parses the cutlist.
2. Downloads assets from R2/MinIO.
3. Builds identity-aware masks (optional).
4. Extracts per-slot video segments in parallel.
5. Applies masks, effects, transitions, overlays, and kinetic text.
6. Mixes audio.
7. Concatenates segments and uploads the final MP4.

Implementation: `services/render-worker/src/render_worker/compiler.py` (`compile_timeline`)

### 5.2 Hardware acceleration

- **NVENC encode**: automatically enabled when `h264_nvenc` is available.
- **CUDA decode**: opt-in via `AVE_USE_HWACCEL=1`.
- Falls back to `libx264`/software decode automatically.

Configuration: `services/render-worker/src/render_worker/compiler.py` (`_video_encode_args`, `_segment_video_args`, `_extract_segment`)

### 5.3 Quality profiles

Offline renders can pick a quality preset:

| Profile | Use case |
|---|---|
| `preview` | Fast 360p drafts |
| `draft` | Iterative editing |
| `demo` | Default social exports |
| `export` | High-quality delivery |
| `archive` | Masters |

Definitions: `services/shared-py/src/shared_py/tuning.py` (`CompilerTuning.QUALITY_PROFILES`)

### 5.4 Clip-order tie-break

When the top two ranked clips are statistically tied, the ranker can fall back to:

- `smart` — keep score order
- `filename` — alphabetical
- `upload` — earliest upload time
- `shuffle` — deterministic per-slot shuffle

Implementation: `services/reason-worker/src/reason_worker/clip_rank.py` (`rank_clips_for_slots`)

### 5.5 Effects & transitions

The compiler supports 15+ effects including zoom, focus pull, freeze frame, speed ramp, shake, glitch, vignette, film grain, color pop, text kinetic, lower third, callout arrow, and SFX.

Definitions: `packages/shared-types/src/effects.ts`, `services/shared-py/src/shared_py/models.py` (`Effect`, effect param models)

Transition mapping to FFmpeg `xfade`: `services/render-worker/src/render_worker/compiler.py` (`XFADE_MAP`)

### 5.6 Subject masking & layered text

- SAM3 masks isolate the protagonist.
- Kinetic text can be composited **behind** the subject when a mask exists, or as a global overlay otherwise.

Implementation: `services/render-worker/src/render_worker/identity_matte.py`, `services/render-worker/src/render_worker/compiler.py` (`_render_layered_text`)

---

## 6. Web / API features

- Clerk authentication
- Project CRUD, asset upload via presigned R2 URLs
- Cutlist prompt editing with JSON Patch diffs
- Render job queueing with SSE progress streaming
- Settings / provider key management

Key files:

- API routes: `apps/api/src/routes/`
- Shared schemas: `packages/shared-types/src/`
- Web editor: `apps/web/src/components/editor/`
- OpenAPI spec: `apps/api/openapi.yaml`

---

## 7. Feature → code quick reference

| Feature | Primary file(s) |
|---|---|
| Reference style matching | `services/style-worker/src/style_worker/workflows.py` |
| Beat detection | `services/ingest-worker/src/ingest_worker/beat_detect.py` |
| Shot detection | `services/ingest-worker/src/ingest_worker/shot_detect.py` |
| Heatmap scoring | `services/ingest-worker/src/ingest_worker/heatmap.py` |
| Style Genome | `services/style-worker/src/style_worker/genome/extract.py` |
| Face detection | `services/ingest-worker/src/ingest_worker/identity.py` |
| Identity clustering | `services/shared-py/src/shared_py/identity_cluster.py` |
| Clip ranking | `services/reason-worker/src/reason_worker/clip_rank.py` |
| Audio mix / ducking | `services/reason-worker/src/reason_worker/audio_mix.py` |
| Transition selection | `services/reason-worker/src/reason_worker/transition_select.py` |
| Render compiler | `services/render-worker/src/render_worker/compiler.py` |
| NVENC / CUDA | `services/render-worker/src/render_worker/compiler.py`, `services/render-worker/src/render_worker/activities.py` |
| Timeline workflow | `services/render-worker/src/render_worker/workflows.py` |
| Offline batch render | `scripts/batch2-offline-render.py` |
