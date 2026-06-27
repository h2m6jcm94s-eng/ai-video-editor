# AI Video Editor — Handoff

> Generated after splitting the working tree into PRs. Last updated: 2026-06-27 (session 4 — fixed repeat bug caused by missing heatmap windows / failed process pool).

---

## 0. Latest Session Snapshot

**Current branch:** `main`  
**Latest commit:** `51a803c` — `fix(repeat): eliminate duplicate source windows in demo render`

### What just happened

- Diagnosed and fixed the demo render repeat bug:
  - **Root cause:** `compute_clip_heatmaps_batch` used `ProcessPoolExecutor`, which crashed on Windows while re-importing PyTorch/CUDA in every spawned worker. Only 37 of 67 clips had heatmap cache files; the rest silently got empty heatmaps.
  - Empty heatmaps caused `_best_window` to return `None`, so every slot received `source_window_start_s = None`, and the compiler fell back to `seek=0` for every clip. Reused clips therefore replayed the exact same opening seconds.
- Applied four fixes:
  1. `services/ingest-worker/src/ingest_worker/heatmap.py` — switched heatmap batching to `ThreadPoolExecutor` and added cache-hit/miss/empty logging. Empty results are no longer cached so they retry on the next run.
  2. `services/reason-worker/src/reason_worker/clip_rank.py` — `_best_window` now hard-excludes already-used windows instead of only penalising them.
  3. `services/render-worker/src/render_worker/compiler.py` — when no heatmap window is available, the compiler now rotates the seek point across the clip based on slot index instead of always seeking to `0.0`.
  4. `scripts/batch2-offline-render.py` — added heatmap coverage validation; raises if >20% of clips have missing/empty heatmaps. Also lazy-imported `probe_video` and `compile_timeline` so spawned heatmap workers do not load boto3/torch stacks.
- Re-rendered batch 2 demo:
  - Full render completed in **47.0s**.
  - Cutlist: **101 slots, 67 unique clips, max reuse 2x**.
  - **True repeats (same clip + same window): 0** (was ~34 before the fix).
  - **Slots with `sourceWindowStartS = None`: 0/101**.

### Test results after merges

```text
Python:    468 passed, 30 skipped
TS shared-types:   7 passed
TS web:           62 passed
TS api:          316 passed
```

### Known working-tree state

- `HANDOFF.md` — modified (this file).
- No untracked wiki files remaining.

### Next priority

- **PR 3 — FastAPI inference server + TensorRT** for batched face detection is the next item in the GPU + Performance Optimizations Tier S plan.

---

## 1. Project Identity

- **Repository:** `h2m6jcm94s-eng/ai-video-editor`
- **Local path:** `e:/work/ai_video_editor`
- **Stack:** pnpm monorepo + uv-managed Python workspace
- **Primary runtime for workers:** Python 3.13.13 (`.venv`)
- **Frontend:** Next.js / TypeScript (`apps/web`)
- **Shared Python models:** `services/shared-py/src/shared_py/`
- **Shared TypeScript schemas:** `packages/shared-types/src/`

---

## 2. Environment Snapshot

Use **only** the `.venv` Python for tests and scripts. The system Python is 3.11.15 and should not be used directly.

| Component | Version / State |
|-----------|-----------------|
| System Python | 3.11.15 |
| Project Python | 3.13.13 (`.venv/Scripts/python`) |
| PyTorch | `torch 2.6.0+cu124`, `torchvision 0.21.0+cu124` |
| CUDA | 12.4, driver 596.36, WDDM |
| GPU | NVIDIA GeForce RTX 4070 Ti SUPER, 16 GB VRAM |
| FFmpeg | 8.1.1 full build with NVENC/AMF support |
| Package manager | `uv` (Python), `pnpm` (Node) |
| Test media | `test files/batch 2/` — Cyberpunk reference AMV, "Let You Down" song, 67 Edgerunners clips |

Verify CUDA is reachable:

```bash
.venv/Scripts/python -c "import torch; print(torch.cuda.is_available())"
```

---

## 3. What Was Just Accomplished

The full working tree (45 changed files) was split into five focused PRs and the original combined state was preserved.

### Completed work

- **Spec #3 adaptive audio ducking** implemented and verified.
- CUDA 12.4 PyTorch stack pinned in `uv.lock`.
- NVENC auto-selection in `RenderConfig` (`h264_nvenc` when available).
- Parallel slot extraction via `ThreadPoolExecutor`.
- CUDA-backed Whisper transcription.
- Test fixes: `n_points` → `num_points`; **342 passed, 29 skipped**.
- Batch 2 render verified: preview in **2.3s**, 30s full render in **5.2s** with valid AAC audio.
- Working tree backed up to `backup/working`.
- Five clean PRs created from `main`.

---

## 4. Branch & PR Map

Each PR is based on `main`. They must be merged **in order** because later PRs depend on shared models and earlier features.

| Order | PR # | Branch | Title | Merge dependency |
|-------|------|--------|-------|------------------|
| 1 | [#176](https://github.com/h2m6jcm94s-eng/ai-video-editor/pull/176) | `feat/setup-shared-deps` | Shared deps/models foundation | **MERGED** |
| 2 | [#177](https://github.com/h2m6jcm94s-eng/ai-video-editor/pull/177) | `feat/ingest-heatmap-pipeline` | Heatmap + beat detection | **MERGED** |
| 3 | [#178](https://github.com/h2m6jcm94s-eng/ai-video-editor/pull/178) | `feat/reason-audio-cutlist` | Audio mix + cutlist + transitions | **MERGED** |
| 4 | [#179](https://github.com/h2m6jcm94s-eng/ai-video-editor/pull/179) | `feat/render-compiler` | Two-pass render compiler | **MERGED** |
| 5 | [#180](https://github.com/h2m6jcm94s-eng/ai-video-editor/pull/180) | `feat/frontend-render-options` | Render options dialog | **MERGED** |

> **Backup branch:** `backup/working` (local and remote) contains the original combined commit `097f69c`. If anything goes wrong, reset to this.

### Updating downstream PRs after merges

Because each branch is based on `main`, after you merge #176 you should update #177, #178, #179, #180; after #177 merge update #178, #179, #180; etc.

```bash
gh pr update-branch 177 --repo h2m6jcm94s-eng/ai-video-editor
```

Or locally:

```bash
git checkout feat/ingest-heatmap-pipeline
git pull origin main
git push
```

---

## 5. Repository State

- **Current branch:** `feat/frontend-render-options`
- **Working tree:** clean (no staged or unstaged changes)
- **Untracked:** this `HANDOFF.md` file only
- **Remote:** `https://github.com/h2m6jcm94s-eng/ai-video-editor.git`

All five feature branches and `backup/working` have been pushed.

---

## 6. Architecture & Data Flow

### Workers

| Worker | Responsibility | Key files |
|--------|---------------|-----------|
| `ingest-worker` | Beat detection, heatmap scoring, shot/quality windows | `services/ingest-worker/src/ingest_worker/beat_detect.py`, `heatmap.py`, `activities.py`, `workflows.py` |
| `reason-worker` | Clip ranking, cutlist generation, transition selection, audio mix | `services/reason-worker/src/reason_worker/clip_rank.py`, `cutlist_gen.py`, `transition_select.py`, `audio_mix.py`, `audio_scoring.py`, `aspect_detect.py`, `activities.py`, `workflows.py` |
| `render-worker` | FFmpeg timeline compilation, two-pass render | `services/render-worker/src/render_worker/compiler.py`, `activities.py`, `workflows.py` |
| `shared-py` | Pydantic models, config, aesthetic utilities | `services/shared-py/src/shared_py/models.py`, `config.py`, `aesthetic.py` |
| `apps/web` | Editor UI | `apps/web/src/components/editor/RenderOptionsDialog.tsx`, `RenderButton.test.tsx`, `apps/web/tests/render-options-dialog.test.tsx` |

### Offline batch-2 pipeline flow

`scripts/batch2-offline-render.py` is a self-contained demo that runs end-to-end:

1. Probe reference video.
2. Detect beats with `detect_beats_librosa`.
3. Compute heatmaps for each user clip.
4. Generate cutlist via `cutlist_gen`.
5. Rank clips and select transitions.
6. Build audio tracks via `build_audio_tracks`.
7. Render with `compile_timeline` (NVENC when available).

---

## 7. Key Technical Decisions

### 7.1 FFmpeg two-pass render

FFmpeg's `sidechaincompress` cannot consume a filter-output sidechain stream when the same graph also contains video filters. The fix is a true two-pass render:

1. **Video-only pass:** extract segments in parallel, compose video, encode to `video_only.mp4`.
2. **Audio/mux pass:** build a pure audio filtergraph, then `ffmpeg -i video_only.mp4 -i song -i dlg1.wav ... -map 0:v -map [a_out] -c:v copy`.

This keeps the audio graph a pure audio chain.

### 7.2 Gated dialogue bus requires `asplit`

The gated dialogue stream is used for **both** the sidechain key and the final mix. In FFmpeg a filter output can only be consumed once, so the `agate` output must be split:

```text
[dlg_raw]agate=...:ratio=10:attack=20:release=200,asplit=2[dlg_gated][dlg_mix]
[music][dlg_gated]sidechaincompress=threshold=0.15:ratio=4:attack=200:release=400[music_ducked]
[music_ducked][dlg_mix]amix=inputs=2:duration=longest:weights='1.0 1.2':normalize=0[a_out]
```

Without `asplit`, the second reference to the gated stream fails with "matches no streams".

### 7.3 Audio input ordering in the mux pass

- Input 0: `video_only.mp4` (copied, no re-encode)
- Input 1: song
- Inputs 2+: per-slot dialogue WAVs
- Maps: `-map 0:v -map [a_out]`

### 7.4 NVENC auto-selection

`RenderConfig` selects `h264_nvenc` when available; fallback is `libx264`. Preview uses `libx264` intentionally for speed/compatibility.

### 7.5 Parallel extraction

Slot segment extraction runs in a `ThreadPoolExecutor` to saturate the NVENC/CUDA pipeline and reduce wall-clock render time.

---

## 8. Files by PR

### PR #176 — `feat/setup-shared-deps`

- `pyproject.toml`
- `uv.lock`
- `scripts/download_models.py`
- `services/ingest-worker/pyproject.toml`
- `services/reason-worker/pyproject.toml`
- `services/shared-py/src/shared_py/aesthetic.py`
- `services/shared-py/src/shared_py/config.py`
- `services/shared-py/src/shared_py/models.py`
- `packages/shared-types/src/cutlist.ts`
- `packages/shared-types/src/schemas.ts`
- `apps/web/src/hooks/useEditor.test.ts`

### PR #177 — `feat/ingest-heatmap-pipeline`

- `infra/docker/Dockerfile.ingest`
- `services/ingest-worker/src/ingest_worker/__main__.py`
- `services/ingest-worker/src/ingest_worker/activities.py`
- `services/ingest-worker/src/ingest_worker/beat_detect.py`
- `services/ingest-worker/src/ingest_worker/heatmap.py`
- `services/ingest-worker/src/ingest_worker/workflows.py`
- `services/ingest-worker/tests/test_heatmap.py`
- `tests/test_beat_detect.py`
- `tests/test_integration_pipeline.py`

### PR #178 — `feat/reason-audio-cutlist`

- `services/reason-worker/src/reason_worker/activities.py`
- `services/reason-worker/src/reason_worker/aspect_detect.py`
- `services/reason-worker/src/reason_worker/audio_mix.py`
- `services/reason-worker/src/reason_worker/audio_scoring.py`
- `services/reason-worker/src/reason_worker/clip_rank.py`
- `services/reason-worker/src/reason_worker/cutlist_gen.py`
- `services/reason-worker/src/reason_worker/transition_select.py`
- `services/reason-worker/src/reason_worker/workflows.py`
- `services/reason-worker/tests/test_aspect_detect.py`
- `services/reason-worker/tests/test_audio_scoring.py`
- `services/reason-worker/tests/test_clip_rank_exhaust.py`
- `services/reason-worker/tests/test_duration.py`
- `services/reason-worker/tests/test_snap_priority.py`
- `services/reason-worker/tests/test_transition_select.py`
- `tests/test_clip_rank.py`
- `tests/test_cutlist_gen.py`

### PR #179 — `feat/render-compiler`

- `services/render-worker/src/render_worker/activities.py`
- `services/render-worker/src/render_worker/compiler.py`
- `services/render-worker/src/render_worker/workflows.py`
- `tests/test_render_compiler.py`
- `scripts/batch2-offline-render.py`

### PR #180 — `feat/frontend-render-options`

- `apps/web/src/components/editor/RenderButton.test.tsx`
- `apps/web/src/components/editor/RenderOptionsDialog.tsx`
- `apps/web/tests/render-options-dialog.test.tsx`

---

## 9. Testing

### Python tests

```bash
uv run pytest
```

Last known result: **342 passed, 29 skipped**.

Run a faster subset (skip slow/integration tests):

```bash
uv run pytest -m "not slow and not integration"
```

### Frontend tests

```bash
cd apps/web
pnpm test
```

### Pre-commit / linting

The repo uses `lint-staged` + `biome`. If you commit normally, hooks run. To bypass (not recommended for final commits):

```bash
git commit --no-verify
```

---

## 10. How to Reproduce the Batch 2 Render

From the repo root:

```bash
.venv/Scripts/python scripts/batch2-offline-render.py --preview
.venv/Scripts/python scripts/batch2-offline-render.py --full
```

Expected outputs go to `test files/batch 2/output/`:

- preview render
- full render
- `cutlist.json`
- `whisper_clips.json`
- `.heatmap-cache/*.heatmap.json`

**Do not commit these output files.** They are large/generated.

---

## 11. Known Issues / Gotchas

1. **FFmpeg sidechain limitation** — already solved by two-pass render. Do not try to put `sidechaincompress` and video filters in the same `ffmpeg` command.
2. **Branch dependencies** — PRs #177–#180 will fail CI/tests until #176 is merged because they rely on the new shared models.
3. **`asplit` is mandatory** for the gated dialogue bus when it feeds both sidechain and final mix.
4. **Audio input ordering** is hard-coded in `compiler.py`; changing it requires updating `_build_audio_filter_v2` and the `dialogue_specs` tuple order.
5. **Working tree must stay clean of `.tmp/`, heatmap cache, and render outputs.** These were removed from the PRs.
6. **GitHub MCP auth is currently broken** in this environment. PRs were created with the `gh` CLI.

---

## 12. Deferred Work

The following items were intentionally **not** completed in this pass:

- Style Genome
- SAM 3 server integration
- Cosmos pipeline
- Auto-LUT per-shot
- RVM v2 final compositing with text z-index

They remain in the idea backlog and should be treated as separate future features.

---

## 13. Next Steps

1. **Merge #176 first.** It has no feature risk; only shared models + dependency pins.
2. **Update downstream PRs** with `gh pr update-branch <number>` after each merge.
3. **Verify CI passes** for #177, then merge.
4. **Verify CI passes** for #178, then merge.
5. **Verify CI passes** for #179, then merge.
6. **Verify CI passes** for #180, then merge.
7. After all PRs are merged, run the full test suite and the batch 2 offline render to confirm nothing regressed.
8. Delete the feature branches once merged; keep `backup/working` until you are confident.

---

## 14. Rollback Plan

If any PR causes issues and you need to return to the original combined working state:

```bash
git fetch origin
git checkout -b recovery/original-combined origin/backup/working
```

This branch contains commit `097f69c` with all 45 original changed files.

---

## 15. Quick Reference Commands

```bash
# Activate Python environment (do not use system Python)
. .venv/Scripts/activate

# Run all Python tests
uv run pytest

# Run batch 2 demo
.venv/Scripts/python scripts/batch2-offline-render.py --preview
.venv/Scripts/python scripts/batch2-offline-render.py --full

# Frontend tests
cd apps/web && pnpm test

# Update a PR branch with latest main
git checkout feat/<branch>
git pull origin main
git push

# View open PRs
gh pr list --repo h2m6jcm94s-eng/ai-video-editor
```

---

## 16. Notes for the Next Agent

- Read `services/shared-py/src/shared_py/models.py` before touching reason/render code. `AudioTrack`, `CutList`, `Slot`, and `RenderConfig` live there.
- The audio filtergraph is the trickiest part of the render. If you change ducking parameters, verify with `volumedetect` and `ffprobe` on the output.
- When adding new Python workers, add their `src` path to `[tool.pytest.ini_options] pythonpath` in `pyproject.toml`.
- The frontend render options dialog depends on shared TypeScript schemas in `packages/shared-types/src/schemas.ts`.
- If you create more PRs, keep them small and based on `main` after the preceding PRs are merged.


---

## 17. V1 Foundation Build — Completed (2026-06-27)

All five foundation PRs were implemented in the working tree in the order requested: **#1 → #4 → #5 → #2 → #3**.

### Branches (not pushed)

| Order | PR | Branch | Status |
|-------|----|--------|--------|
| 1 | Identity-aware matting | `feat/identity-aware-matting` | Implemented |
| 4 | Style Genome v0 | `feat/style-genome-v0` | Implemented |
| 5 | Adaptive audio ducking fix | `fix/audio-ducking-correctly` | Implemented |
| 2 | Z-index text compositing | `feat/zindex-text-compositing` | Implemented |
| 3 | Anticipation + momentum | `feat/anticipation-momentum` | Implemented |

> These were implemented directly on `main` in the local working tree; no git branches were created or pushed. Use `git diff` and `git status` to review.

### Test results

```bash
uv run pytest
```

**447 passed, 30 skipped, 0 failed.**

TypeScript checks:
- `pnpm typecheck` — clean
- `pnpm --filter @ai-video-editor/api test` — 316 passed
- `pnpm --filter @ai-video-editor/web test` — 62 passed

### New high-level capabilities

1. **Identity-aware matting** — per-clip face extraction (InsightFace), project-level DBSCAN clustering, protagonist picking, identity matte generation wired into render activity. Clips without the protagonist skip matting.
2. **Style Genome v0** — 50-feature reference-video fingerprint across 5 families (cut_rhythm, motion, dwell, audio_align, composition) with JSON output and dedicated workflow/activity.
3. **Adaptive audio ducking fix** — per-dialogue noise gate before mixing, separate gated sidechain key bus, safety limiter. The per-slot music gain curve now uses an `asendcmd` command file instead of a giant nested `if(between(t,...))` expression, which FFmpeg's audio evaluator rejected on songs with many slots.
4. **Z-index text compositing** — kinetic text rendered behind the protagonist when an identity matte exists; falls back to text-on-top otherwise. `bold_bounce` preset implemented.
5. **Anticipation + momentum** — optical-flow-based conservation of momentum reranking and anticipation offsets that land cuts ~333 ms before motion peaks.

### Known limitations / notes

- SAM3 is unavailable in this environment, so real identity mattes are not generated. The code gracefully skips mask generation but still populates `identity_ids_present`. When SAM3/HF access is available, the same path will produce masks.
- FFmpeg `drawtext` hangs on the Windows FFmpeg 8.1.1 build during the behind-subject layered compositing test, so the layered path is unit-tested by asserting the produced filter graph. The graph itself was validated against FFmpeg on a simpler synthetic input.
- A pre-existing flaky Windows subprocess issue (`WinError 6` / invalid handle) occasionally causes `TestRenderability` or `TestEndToEndSmoke` integration tests to fail when run in the full suite, but they pass in isolation. It is unrelated to these changes.
- `scripts/batch2-offline-render.py` hardcoded the song as `.mp3`, but the fixture is actually `.flac`. Fixed the script to use `.flac`.
- `scripts/batch2-offline-render.py --preview --skip-heatmap` now completes successfully in ~1.5s and produces a valid H264/AAC MP4.
- Full-duration batch 2 render (`--skip-heatmap`, no `--duration`) completed successfully in **30.7s**, producing a 1920×1080 30fps H264/AAC MP4 of length 03:46.
- Without `--skip-heatmap`, the script hits a memory allocation error inside the pre-existing parallel heatmap computation (`ProcessPoolExecutor` + `cv2.VideoCapture`) on this Windows environment.
- `requires-python` was bumped from `>=3.10` to `>=3.11` because `onnxruntime-gpu>=1.27.0` requires Python 3.11+.

### Next steps

1. Visually inspect the full batch 2 render at `test files/batch 2/output/output.mp4` to confirm the new features feel right.
2. Create GitHub issues for each PR per `CLAUDE.md` (optional for solo-founder velocity, but recommended for audit trail).
3. Split the working tree into the five branches above and open PRs when ready.
4. Re-enable CUDA providers for InsightFace once `cublasLt64_13.dll` is available; until then CPU fallback works.
