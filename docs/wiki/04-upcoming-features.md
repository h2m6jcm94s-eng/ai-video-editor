# 04 — Upcoming Features

> Roadmap summary and a deep-dive on the next two features we are building.
>
> Source documents: [`ROADMAP.md`](../../ROADMAP.md), [`PLAN.md`](../../PLAN.md), [`HANDOFF.md`](../../HANDOFF.md), [`optimisations.md`](../../optimisations.md).
> Code paths are relative to the repo root; line numbers refer to `main` as of the last handoff.

---

## 1. Roadmap at a glance

The product is following the four-layer plan in `ROADMAP.md`:

| Layer | Timeframe | Theme | Key highlights |
|---|---|---|---|
| **Layer 1 — Demo** | Days 1–14 (ends 2026-07-04) | Reference-driven AI editor | Prompt loop, color grade, transitions, focus pulls, text overlays, NVENC render. **Done.** |
| **Layer 2 — V1** | ~3 months post-funding | Killer feature set (12 Tier A + 4 Tier B) | J-cuts/L-cuts, stabilization, auto-reframe 9:16/16:9/1:1, AI voice-over, text-based editing, AI b-roll search, auto-translation + lip-sync, optical-flow slow-mo, voice isolation, AI thumbnails, loudness normalization, auto-color match, plus SAM 2 rotobrush, inpainting, auto-cut, direct publish. |
| **Layer 3 — V2** | 6–12 months | Moat building | Real-time generative b-roll (Veo/Kling/Runway), AI VFX assistant, character consistency, real-time collaboration, begin SAM 2 productionization. |
| **Layer 4 — V3** | 12–24 months | Saksham’s vision | 3D Gaussian Splatting reconstruction, DROID-SLAM camera tracking, camera pose transfer, diegetic AI sound design. |

The next engineering priority comes from `HANDOFF.md` §0: **PR 3 — FastAPI inference server + TensorRT** for batched face detection. After that, the highest-value Layer 2 / Tier A feature that fits the current architecture is **J-cuts and L-cuts**.

---

## 2. Feature 1 — FastAPI inference server + TensorRT for batched face detection

### 2.1 What it is and why it matters

Face detection is already part of the pipeline: the ingest worker samples frames from user clips, runs InsightFace, caches `{clip}.faces.json`, and the reason worker clusters embeddings with DBSCAN to pick project protagonists. Today that model lives inside `services/ingest-worker` and is loaded per-process, per-call. Each frame is still passed individually to `FaceAnalysis.get`, so the GPU is under-utilized and every worker pays a cold-start cost.

This feature adds a dedicated **FastAPI inference server** that:

1. Keeps the InsightFace detection (and optionally recognition) model in VRAM across requests.
2. Accepts a batched tensor of frames from many clips in one HTTP call.
3. Compiles the detection model to **TensorRT** and caches the engine on disk.
4. Returns the same `FaceDetection` shape the rest of the pipeline already consumes.

Why it matters (from `optimisations.md` §GPU Tier S #3–#5):

- TensorRT removes eager-mode PyTorch overhead: **2–3× faster face detection**, and the total heatmap/analysis pass for a 67-clip project drops from ~4 min to ~1 min.
- Persistent serving removes **30–60 s of cold-start overhead per render**.
- True batching across clips (batch = 32–64) gives another **4–6× throughput win**.

### 2.2 User-facing behavior

- Uploading clips feels faster: face extraction no longer reloads the model for every worker invocation.
- Identity-aware features (protagonist matting, smart bins, "find clips with Lucy") become cheap enough to run by default.
- If the inference server is offline or TensorRT is unavailable, the pipeline silently falls back to the current local InsightFace path.

### 2.3 Technical design

#### New files

| File | Responsibility |
|---|---|
| `services/inference-server/src/inference_server/main.py` | FastAPI app with `POST /detect` and `POST /embed` endpoints, request validation, batching queue. |
| `services/inference-server/src/inference_server/engine.py` | Load InsightFace models, build / load cached TensorRT engines, run batched inference, normalize/pad inputs. |
| `services/inference-server/src/inference_server/models.py` | Pydantic request/response schemas (`FaceDetectRequest`, `FaceDetectBatch`, `FaceDetectResponse`). |
| `services/inference-server/src/inference_server/trt_cache.py` | ONNX export of the detection network + TensorRT engine caching keyed by model name / batch size / precision. |
| `services/inference-server/Dockerfile` | GPU-enabled container (`nvidia/cuda` base + TensorRT + uv). |
| `services/inference-server/tests/test_engine.py` | Unit tests for batching, padding, and fallback. |
| `services/ingest-worker/src/ingest_worker/inference_client.py` | Thin HTTP client that POSTs a buffered batch to the server and maps responses back to `FaceDetection`. |

#### Changes to existing files

- `services/ingest-worker/src/ingest_worker/identity.py`
  - Add a `_process_frame_batch_remote(...)` path that is used when `INFERENCE_SERVER_URL` is set.
  - Keep `_process_frame_batch(...)` as the local InsightFace fallback (lines 84–125).
  - `extract_faces_from_clips` (lines 158–221) decides local vs. remote based on env.
- `pyproject.toml` / `uv.lock`
  - Add `fastapi`, `uvicorn[standard]`, `python-multipart`, `tensorrt`, `onnx`, `onnxruntime-gpu` to the inference server package; keep the ingest worker dependency on `httpx` only.
- `docker-compose.yml` / `infra/docker/`
  - Add an `inference-server` service with GPU reservations and a shared model-cache volume.
- `apps/api/src/routes/internal.ts`
  - Optionally expose `POST /api/internal/assets/:assetId/extract-faces` so the upload workflow can trigger face extraction asynchronously (similar to the existing probe endpoint at line 188).

#### Data contract

The server returns the same fields as the current `FaceDetection` dataclass (`clip_id`, `frame_idx`, `t_s`, `bbox`, `bbox_norm`, `embedding`, `confidence`, `face_area_ratio`), so downstream consumers need no changes.

### 2.4 Where it plugs in

- **Face extraction entry point** — `services/ingest-worker/src/ingest_worker/identity.py:158` (`extract_faces_from_clips`). This is the only place that needs to choose local vs. remote inference.
- **Local model cache** — `services/ingest-worker/src/ingest_worker/identity.py:61` (`_get_face_app`). Becomes the fallback path; its global singleton is already designed so only one session is created per process.
- **Frame buffering** — `services/ingest-worker/src/ingest_worker/identity.py:202`. The existing `max_batch_frames=64` buffer was intentionally added as the insertion point for a batched backend.
- **Cache writer** — `services/ingest-worker/src/ingest_worker/identity.py:245` (`_write_face_cache`) and `ensure_faces_for_clips` (line 270). Results are still written to `{clip}.faces.json` so clustering is decoupled from inference.
- **Protagonist clustering** — `services/reason-worker/src/reason_worker/protagonist_pick.py:21` (`load_faces_for_project`) and line 44 (`select_protagonists`). These read the cache and run DBSCAN; they are unaffected by where the detections came from.
- **Render matte path** — `services/render-worker/src/render_worker/identity_matte.py` consumes `slot.identity_ids_present`; it only cares that the cache exists.
- **Ingest activity hook** — `services/ingest-worker/src/ingest_worker/activities.py:82` (`compute_clip_heatmap_activity`). A new `extract_faces_activity` would sit alongside it and call `ensure_faces_for_clips`.

### 2.5 Open questions and risks

| Risk | Mitigation |
|---|---|
| TensorRT engine conversion for InsightFace’s detection + recognition networks is non-trivial and version-sensitive. | Start with detection only; use ONNX Runtime TensorRT execution provider first; cache engines; keep local CPU/CUDA fallback. |
| Dynamic input shapes (different frame resolutions across clips) force engine rebuilds. | Pad/letterbox frames to a fixed server-side resolution (e.g., 640×640) before inference, matching InsightFace’s `det_size`. |
| Network overhead may hurt small projects. | Use the remote path only when `INFERENCE_SERVER_URL` is configured; local inference remains the default for single-clip or dev workflows. |
| Windows dev environment lacks TensorRT today (`cublasLt64_13.dll` issue noted in `HANDOFF.md`). | Build and test the server inside the Docker GPU container first; Windows ingest worker falls back to local InsightFace automatically. |
| Concurrent requests can OOM VRAM if the queue is unbounded. | Add a server-side semaphore and explicit `max_batch_size`; reject or queue requests rather than crash. |
| Model update invalidates cached engines. | Include model hash + TensorRT version in the cache key. |

---

## 3. Feature 2 — J-cuts and L-cuts

### 3.1 Why this is the right next feature

Layer 2 / Tier A has many strong candidates. **J-cuts and L-cuts** are chosen as the second feature because:

- **Highest ROI in Tier A**: `ROADMAP.md` rates them "★★★ Biggest single 'amateur → pro' jump" with an effort of only **🟢 3 days**.
- **Fits the existing architecture**: the render compiler already builds a two-pass audio filter graph with per-slot dialogue extraction, delays, gates, and sidechain ducking. Adding audio lead-in/trail-out is a schema + timing change, not a new subsystem.
- **Builds on recent work**: the adaptive audio ducking fix in `HANDOFF.md` §17.2 and the two-pass render in `compiler.py` are exactly the right foundation.
- **Low regression risk**: it is additive; without the new fields the pipeline behaves identically.

Other Tier A options were considered:

- **Auto-reframe vertical/square** is high impact but requires MediaPipe subject tracking and changes the render dimensions/pan logic (~1 week).
- **Text-based editing** is the Descript-killer, but it needs a transcript editor UI, word-level Whisper alignment, and cutlist synchronization (~1.5 weeks).
- **J-cuts/L-cuts** require only a few new slot fields and audio-mix math.

### 3.2 What it is and why it matters

A **J-cut** lets the *next* clip’s audio start before its video appears. An **L-cut** lets the *previous* clip’s audio continue after its video has ended. They are the single most common technique that separates professional edits from automated slideshows.

### 3.3 User-facing behavior

- In the render options / cutlist editor the user can toggle **"Use J-cuts / L-cuts"** or edit per-slot values.
- The AI can auto-decide offsets based on shot type, dialogue presence, and transition duration.
- Exported videos have smoother audio continuity across cuts, especially for dialogue-driven content (vlogs, interviews, podcasts).

### 3.4 Technical design

#### Schema changes

Add two new fields to every slot:

```text
audio_lead_in_s   : float  # audio of this slot starts before its video
audio_trail_out_s : float  # audio of this slot continues after its video ends
```

These fields are added to:

- `services/shared-py/src/shared_py/models.py` — `Slot` (line 158).
- `packages/shared-types/src/schemas.ts` — `slotSchema` (line 72).
- `packages/shared-types/src/cutlist.ts` — `buildInitialCutList` defaults to `0`.

#### New reasoning module

- `services/reason-worker/src/reason_worker/jl_cut_planner.py`
  - Proposes `audio_lead_in_s` / `audio_trail_out_s` per slot.
  - Inputs: shot type, transition duration, whether the slot has dialogue, and whether adjacent slots also have dialogue.
  - Caps offsets to the available source handle before/after the selected source window.
  - Prevents two dialogue tracks from overlapping unless explicitly requested.

#### Audio mix changes

- `services/reason-worker/src/reason_worker/audio_mix.py`
  - `build_audio_tracks` (line 186) reads the new slot fields.
  - `_dialogue_segments_for_slot` (line 94) expands the extracted window by the lead-in / trail-out, clamped to clip boundaries.
  - Dialogue `AudioTrack` start/end are shifted so the audio overlaps the adjacent slot while the video stays at `slot.start_s`.

#### Render compiler changes

- `services/render-worker/src/render_worker/compiler.py`
  - `_extract_dialogue_audio` (line 128) extracts `duration + lead_in + trail_out` instead of the raw slot duration.
  - `_build_dialogue_bus` (line 176) already supports per-track delays; it will position the longer extract correctly using the slot’s `start_s - lead_in` offset.
  - `_build_audio_filter_v2` (line 859) adds per-dialogue fade/gate around the overlap region so the overlap does not create audible pops.
  - The existing video xfade overlap (line 1321, `min(0.3, ...)`) should be coordinated with the audio offsets: the audio overlap should generally be ≥ the video transition duration.

#### Frontend changes

- `apps/web/src/components/editor/RenderOptionsDialog.tsx` — add a toggle and per-slot expansion.
- `packages/shared-types/src/schemas.ts` — update `slotSchema` validation.

#### Tests

- `services/reason-worker/tests/test_audio_mix.py` — verify lead-in/trail-out produce correct `AudioTrack` times.
- `services/render-worker/tests/test_render_compiler.py` — verify the generated audio filter graph contains the expected delays and the output duration is not stretched.

### 3.5 Where it plugs in

- **Shared slot model** — `services/shared-py/src/shared_py/models.py:158` (`Slot`). New optional fields here propagate to every worker.
- **TypeScript schema** — `packages/shared-types/src/schemas.ts:72` (`slotSchema`). Keeps frontend, API, and worker contracts consistent.
- **Initial cutlist builder** — `packages/shared-types/src/cutlist.ts:22` (`buildInitialCutList`). Defaults both offsets to `0`.
- **Dialogue discovery** — `services/reason-worker/src/reason_worker/audio_mix.py:94` (`_dialogue_segments_for_slot`). Expands the search window.
- **Track builder** — `services/reason-worker/src/reason_worker/audio_mix.py:186` (`build_audio_tracks`). Emits `AudioTrack` objects with the overlap baked into `start_s` / `end_s` and `source_start_s` / `source_end_s`.
- **Dialogue extraction** — `services/render-worker/src/render_worker/compiler.py:128` (`_extract_dialogue_audio`). Extracts the longer source region.
- **Dialogue bus delay** — `services/render-worker/src/render_worker/compiler.py:176` (`_build_dialogue_bus`). Uses `track.start_s` to delay each extract to the correct timeline position.
- **Audio filter graph** — `services/render-worker/src/render_worker/compiler.py:859` (`_build_audio_filter_v2`). Applies fade/gate to the overlapping edges.
- **Render trigger** — `apps/api/src/routes/renders.ts`. Render options can pass `enableJlCuts: true` through to the worker.
- **Transition timing** — `services/reason-worker/src/reason_worker/transition_select.py`. J/L offsets should be derived from or capped by the selected transition duration.

### 3.6 Open questions and risks

| Risk | Mitigation |
|---|---|
| The selected source window may not have enough handle media before/after it. | Clamp offsets to `max(handle_before, handle_after)` per clip; skip J/L cut for that boundary if insufficient. |
| Overlapping dialogue from two adjacent slots can create muddy audio. | Default policy: only one active dialogue track at a time; allow overlap only when the user explicitly enables it or when one slot is music-only. |
| Audio offsets could conflict with the video xfade overlap. | Coordinate offsets with the transition duration used by `compiler.py:1318` (`xfade=transition=...:duration=...`). |
| Negative or floating-point delays in `_build_audio_filter_v2` could break FFmpeg. | Clamp all delays to `>= 0`; round to milliseconds. |
| UI adds complexity for a feature users may want auto-enabled. | Ship an **Auto** toggle first; manual per-slot controls can come later. |

---

## 4. Suggested implementation order

1. **FastAPI inference server + TensorRT** — PR 3 from `HANDOFF.md`; unblocks all identity-aware features and lowers per-render cost.
2. **J-cuts / L-cuts** — highest-value Tier A feature; builds directly on the two-pass audio render completed in the last milestone.

After these land, the next candidates from Layer 2 are **auto-reframe** (multi-format output) and **loudness normalization**, both of which are small, self-contained wins that plug into the same compiler and schema layer.
