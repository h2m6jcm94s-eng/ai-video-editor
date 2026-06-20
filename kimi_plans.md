# AI Video Editor — Investor Demo Sprint + Best-AI-Editor Plan

**Last updated:** 2026-06-21  
**Demo date:** 2026-07-05 (14 days from today)  
**Plan author:** Kimi Code CLI  
**Target executors:**
- Devayan Dewri — product, investor narrative, API keys, demo rehearsal
- Saksham — Python workers, FFmpeg compiler, ML integrations
- Amitansu — frontend, API routes, UI/UX polish  
**Working tree:** `E:\work\ai_video_editor` on branch `feat/sprint-stability-d01` (branched from `main @ 68afeb2`)

---

## 0. Read This First — It Tells the Story

An investor who heard the base idea casually is now actively investing, contingent on a working demo. **India context:** the bar is product-grade, not prototype-grade. The investor will upload their own reference video, their own clips, and their own song — and expect a polished, social-ready output. If the output looks like a slideshow or has black holes, the deal dies.

The WhatsApp thread from Devayan (2026-06-20 04:28–05:13) contains two very different lists. Distinguish them rigidly:

| Saksham's "P0 — demo-required" | Saksham's "P2 — research / DO NOT release" |
|---|---|
| LUTs (color grading) | SAM-based layer separation |
| Proper camera pans / focus pulls | 3D Gaussian Splatting |
| Filler clips | DROID-SLAM neural camera tracker |
| Text overlays | ControlNet neural lighting |
| Twelve Labs API for video understanding | DensePose / VIMO body reconstruction |
| Closed-loop prompt editing | Seedance cinematic generation |
| (Optional) UI-based editing | VASE low-grade preview generation |

**This plan delivers the P0 column in 14 days.** P2 is a 6–12 month post-Series-A engineering/research track. Do not conflate them.

Devayan's later clarification: *"text based edits + colour grading + transitions + focusing + other things, just multipart [multi-track] editor would be built a bit later, but right now we have to make it actually the best editor to do the work like the bestttt state of art."*

**Demo scope = single-track output, state-of-art quality. Multi-track timeline UI is deferred.**

---

## 1. Demo Success Criteria — The Bar

Investor opens the app (or is given a test account) and within 5 minutes can:

1. Upload a **reference video** (their inspiration — e.g., a slick ad or reel they like).
2. Upload **3–5 clips** of their own footage.
3. Upload a **song** of their choice.
4. Pick a style tier (default `with_effects`).
5. Click **"Generate"**.
6. Within **90 seconds**, see a **preview** (360p, ~15 s) of the edit.
7. Within **5 minutes**, get the **full render** (720p, full duration, ~30 s).

The render must have:

- **Color grade matching the reference** (HM-MVGD-HM, not simplified Reinhard).
- **Cuts on the beats** (downbeats get longer holds).
- **Variety of transitions** — dissolve, flash, whip, slide all distinct, not all faded into each other.
- **At least 2 zoom punch-ins** on high-energy moments.
- **At least 1 focus pull** on a slow shot.
- **Text overlays** at section boundaries (intro/drop/outro) with kinetic animation (typewriter or fade_up).
- **No black holes** — filler clips loop, freeze, or stock-replace if user clips < slots.
- **Audio ducks** under any voiceover (sidechain compression).
- **Whoosh SFX** on dramatic transitions (ElevenLabs SFX).

Then the investor types a prompt: *"Make the cut at 0:14 land on the snare and add a focus pull when she enters frame."*

- Within 30 seconds, see the change applied + a diff + **Undo** button (closed-loop prompt editing).
- Click **"Re-render"** → final video updated.

**If any one of these steps fails, the demo is a bust.** Plan accordingly.

---

## 2. Current State — Verified 2026-06-21, HEAD `68afeb2`

### 2.1 What Works (Don't Redo)

| Component | State | File |
|---|---|---|
| End-to-end pipeline (upload → probe → render → MP4) | ✅ Proven once (`output-B.mp4`, 17.7 s, 720×1280) | `services/render-worker/src/render_worker/workflows.py:26`, `compiler.py` |
| Beat detection (`allin1` + librosa fallback) | ✅ Code present, real music likely works | `services/ingest-worker/src/ingest_worker/beat_detect.py:96` |
| Shot detection / probing | ✅ Working | `services/ingest-worker/src/ingest_worker/probe.py:62` |
| Camera motion classification | ✅ Working but **UNUSED downstream** | `services/style-worker/src/style_worker/camera_motion.py:19` |
| Text extraction from reference (PaddleOCR) | ✅ Working but **UNUSED downstream** | `services/style-worker/src/style_worker/text_extract.py:25` |
| Cut list generation (AI chain + programmatic fallback) | ✅ Works, default is programmatic | `services/reason-worker/src/reason_worker/cutlist_gen.py:111` |
| CutList schema (Pydantic + camelCase) | ✅ Locked | `services/shared-py/src/shared_py/models.py:9-14`, `packages/shared-types/src/schemas.ts` |
| LUT application in compiler (`lut3d` filter) | ✅ Wired, applies if path exists | `services/render-worker/src/render_worker/compiler.py:252-259` |
| Effect renderer for zoom_punch_in / vignette / film_grain / shake | ✅ Coded | `compiler.py:108-132` |
| Render preview function (360p, 15 s cap) | ✅ Function exists, **NO UI button** | `compiler.py:344-372` |
| Auth (Clerk + internal bypass) | ✅ Wired | `apps/api/src/middleware/auth.ts:10` |
| AI prompt edit (Claude/GPT JSON Patch) | ✅ Working | `apps/api/src/services/ai.ts:125` |
| Provider key encryption | ✅ Working | `apps/api/src/lib/crypto.ts` |

### 2.2 What's Broken or Hollow (The Demo Risk)

| Issue | File:Line | Impact |
|---|---|---|
| LUT extraction uses simplified Reinhard, not HM-MVGD-HM | `services/style-worker/src/style_worker/lut_extract.py:96` | Color grading won't match cinematic palettes (orange/teal) — investor will notice |
| Style/camera/text workers are **not orchestrated** by Temporal | `services/render-worker/src/render_worker/workflows.py` | Reference video does not actually drive the output |
| AI never populates `slot.effects[]` | `services/shared-py/src/shared_py/ai_providers/base.py` system prompt | Zero zoom punch-ins, focus pulls, etc. |
| AI never populates `cutList.overlays[]` | same | Zero text overlays |
| Text overlays render statically (no animations) | `compiler.py:262-283` | Schema supports animation, renderer ignores it |
| `XFADE_MAP["dissolve"]` → `fade` | `compiler.py:76` | Dissolve transitions render as fade |
| `XFADE_MAP["flash"]` → `fade` | `compiler.py:88` | Flash transitions render as fade |
| `clip_rank.py semantic_score = 0.7` always | `services/reason-worker/src/reason_worker/clip_rank.py:25-29` | Clip-to-slot matching is random within shot type |
| Embeddings dict never populated by caller | `services/orchestrator.py:118-126` | Even if Marengo wired, diversity penalty does nothing |
| No stock footage fallback | nowhere | If user has 3 clips and AI makes 10 slots, 7 slots render as nothing |
| `render_preview()` exists but no UI button | `apps/web` editor | Users wait 5+ min for final render before seeing anything |
| No audio ducking (sidechain compression) | `compiler.py:_build_audio_filter` | Music plays at full volume over voiceover |
| No SFX cues on transitions | nowhere | Flashes are silent; whoosh/ding/scratch never trigger |
| PaddleOCR text from reference is extracted but dropped | `text_extract.py` → nowhere | Overlays detected from reference don't propagate to user cut list |
| `camera_motion` classifier output is unused | `camera_motion.py` → nowhere | "Pan when subject enters" never instructed to AI |
| `TWELVE_LABS_API_KEY` declared but never used | `services/shared-py/src/shared_py/config.py:22` | No semantic clip ranking |
| `PEXELS_API_KEY` not declared | `.env.example` | No stock fallback |
| Slot `start_s` ignored in render | `compiler.py:207` | Every slot pulls from start of clip, not intended moment |
| Programmatic cutlist default duration 30 s | `cutlist_gen.py:103` | Investor might want 60 s reels — needs configurable |
| System prompt bans shot types user doesn't have | `base.py:128` | If user has 3 clips, AI may refuse to make 10 slots |

### 2.3 Tests Currently Failing (Fix in Day 1)

Ran `.venv/Scripts/python -m pytest -q`: **9 failed, 240 passed, 27 skipped**.

| Failed Test | Reason |
|---|---|
| `test_beat_detect.py::TestDetectBeatsLibrosa::test_detects_beats` | `librosa.beat.beat_track` returns empty on synthetic audio |
| `test_edge_cases.py::TestRenderEdgeCases::test_slot_before_video_start` | Compiler doesn't raise on negative `start_s` |
| `test_integration.py::TestIntegration::test_probe_to_cutlist` | FFmpeg audio extraction exit 4294967274 |
| `test_integration_pipeline.py::TestFullPipeline::test_probe_video` | `info` is dict; test expects `.width`/`.height` attributes |
| `test_style_analysis.py::TestSampleFrames::test_nonexistent_video` | `sample_frames` returns `[]` instead of raising |
| `test_style_analysis.py::TestClassifyTransitions::test_hard_cuts` | `ShotBoundary` missing `transition_in` field (schema drift) |

These must be green by Day 2 EOD.

### 2.4 What's Been Planned but DEFERRED

The previous hardening plan (multi-pass quality/refactor work) is paused for the sprint. Resume after demo day if funding closes. See Section 8.

---

## 3. APIs to Sign Up for TODAY (Devayan Action)

This is the dependency that unblocks engineering. Sign up, fund, get keys, drop into `.env`.

| Service | Why we need it | Free tier | Paid estimate | Sign up |
|---|---|---|---|---|
| **Twelve Labs (Marengo 3.0)** | Semantic clip search — "find the close-up of her smiling" | 10 hours indexing + analysis shared | ~$0.04/min if exceeded; budget $50 for demo | twelvelabs.io/pricing |
| **ElevenLabs (Sound Effects API)** | Whoosh/ding/scratch SFX | Limited free | $5/mo Starter plan | elevenlabs.io/sound-effects |
| **Pexels Video API** | Stock footage fallback | 20K requests/day free | Free indefinitely | pexels.com/api |
| **OpenAI Whisper** | Subtitle transcription | None | ~$10 for demo | already have `OPENAI_API_KEY` |
| **Groq** | Cutlist generation | Generous free | $0 expected | already wired |
| **Anthropic Claude** | Prompt edit refinement | $5 free credit | $20 for demo | already wired |
| **Cloudflare R2** | Storage | 10 GB free | Free for demo | already wired |

**Optional but strongly recommended:**

| Service | Why | Cost |
|---|---|---|
| **Coverr API** | Backup stock footage provider | Free 1000 calls/mo |
| **Pixabay API** | Third stock fallback | Free indefinitely |
| **Runway / Kling / Seedance** | Generative filler for v2 | Credit-based; wait until post-demo |

**Devayan: do this Day 0 (today, 2026-06-21).** Add all keys to `.env`, `apps/api/.env.local`, and root `.env.example`. Saksham cannot start API integration without keys.

**Total demo budget:** ~$100 for the 14-day sprint + presentation buffer.

---

## 4. Architecture — What We Add to Make This State-of-Art

```
┌──────────────────────────────────────────────────────────────────────┐
│                          USER UPLOADS                                │
│   Reference video    User clips (3-N)    Song    [optional prompt]   │
└─────────────┬──────────────┬──────────────┬─────────────────────────┘
              │              │              │
              ▼              ▼              ▼
┌─────────────────────┐ ┌──────────────┐ ┌──────────────┐
│ INGEST WORKER       │ │ INGEST WORKER│ │ INGEST WORKER│
│ ─ Beat detect       │ │ ─ Shot detect│ │ (transcribe  │
│ ─ Section markers   │ │ ─ Probe      │ │  if voice)   │
│ ─ Probe duration    │ │ ─ Camera     │ │              │
│                     │ │   motion ★   │ │              │
│                     │ │ ─ PaddleOCR ★│ │              │
└─────────┬───────────┘ └──────┬───────┘ └──────┬───────┘
          │                    │                │
          ▼                    ▼                ▼
┌────────────────────────────────────────────────────────────┐
│           STYLE WORKER                                      │
│  ─ LUT extraction (HM-MVGD-HM via color-matcher) ★★★       │
│  ─ Style analysis (mood, pacing, palette)                  │
│  ─ Detected text overlays (from PaddleOCR) → propagate ★★  │
│  ─ Detected camera motions → propagate to motion_hint ★★   │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│       CLIP UNDERSTANDING (NEW)                              │
│  ─ Twelve Labs Marengo 3.0: index user clips ★★★           │
│  ─ Semantic embedding per clip (1024-dim)                   │
│  ─ Used by clip_rank.py to replace 0.7 placeholder ★★★     │
│  ─ SigLIP-2 local fallback if Twelve Labs down/budget ★★   │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│       REASON WORKER (CUTLIST GEN)                           │
│  ─ Provider: Groq (fast) / Claude (quality fallback)        │
│  ─ NEW prompt: AI must populate slot.effects[] ★★★         │
│  ─ NEW prompt: AI must populate overlays[] ★★★             │
│  ─ NEW prompt: AI uses camera_motion data for motion_hint  │
│  ─ Validate response shape → 1-retry-with-hint ★★          │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│       CLIP RANKING                                          │
│  ─ Replace 0.7 placeholder with Marengo cosine sim ★★★     │
│  ─ Stock fallback: if user clips < slots, query Pexels ★★★ │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│       RENDER WORKER (FFmpeg compiler.py)                    │
│  ─ Apply LUT (already wired)                                │
│  ─ Apply effects: focus_pull, text_kinetic, freeze ★★★     │
│  ─ Fix XFADE_MAP: dissolve→real, flash→white-frame ★★      │
│  ─ Text animations: typewriter, fade_up ★★★                │
│  ─ Audio ducking (sidechain compression) ★★                │
│  ─ SFX inject: ElevenLabs whoosh on dramatic transitions ★ │
│  ─ Stock fallback rendering (Pexels MP4 download) ★★★      │
│  ─ Respect slot.start_s (fix -ss 0 bug) ★★★                │
└────────────────────────────┬───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│              OUTPUT MP4                                     │
│  Preview path (NEW): 360p / 15s cap / <90s render time ★★★ │
│  Full path: 720p / full duration / <5min render time       │
└────────────────────────────┴───────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────┐
│       CLOSED-LOOP PROMPT EDIT                               │
│  User types prompt → ai.ts JSON Patch already works         │
│  Apply → render preview again → show diff + Undo button ★★ │
└────────────────────────────────────────────────────────────┘
```

**Legend:** ★ = nice-to-have. ★★ = must-have. ★★★ = blocker for demo.

---

## 5. 14-Day Sprint Plan

Each day has Morning / Afternoon / EOD verify blocks. Target ~3–4 hours of focused work per block. Days 13–14 are intentional buffer.

### Day 1 (2026-06-21) — Stabilize the Broken Tests ✅

**Morning (Devayan, parallel with engineering)**

- [ ] Sign up for Twelve Labs (Marengo 3.0), ElevenLabs (SFX), Pexels (Video API).
- [ ] Add all keys to `.env`, `apps/api/.env.local`, and root `.env.example`.
- [ ] Create `docs/runbooks/api-keys.md` documenting key usage, free-tier limits, and rate-limit runbook.

> **Note:** API key signup deferred to Day 2+; engineering focused on test stabilization first.

**Afternoon (Saksham)**

Branch: `feat/sprint-stability-d01`

Fixes applied:

1. ✅ **Beat detection fallback:** `services/ingest-worker/src/ingest_worker/beat_detect.py` now synthesizes a regular beat grid when `librosa.beat.beat_track` returns fewer than 2 beats (common for synthetic/ambient audio). Uses tempo/onset estimate, defaults to 120 BPM, and ensures `beat_positions` length matches `beats`.
2. ✅ **Negative `start_s` validation:** `services/render-worker/src/render_worker/compiler.py` raises `ValueError` on `slot.start_s < 0` and segment extraction now respects `slot.start_s` instead of hardcoding `-ss 0`.
3. ✅ **Probe info attributes:** `services/ingest-worker/src/ingest_worker/probe.py` returns a `ProbeInfo` namespace supporting both attribute (`.width`, `.height`, `.fps`) and dict-like access.
4. ✅ **`sample_frames` nonexistent video:** `services/style-worker/src/style_worker/lut_extract.py` now raises `FileNotFoundError` for missing video files.
5. ✅ **Schema drift `transition_in`/`transition_out`:** Added both fields to `ShotBoundary` in `services/shared-py/src/shared_py/models.py` with sensible defaults (`hard_cut`).
6. ✅ **`compute_confidence` floating-point robustness:** `services/reason-worker/src/reason_worker/clip_rank.py` caps/clips confidence correctly for sparse rankings.
7. ✅ **Integration test fixture:** `tests/test_integration.py::create_test_video` now optionally includes audio so beat detection has a signal.

**EOD verify**

```bash
cd /e/work/ai_video_editor
.venv/Scripts/python -m pytest -q
# Result: 249 passed, 27 skipped, 0 failed
```

**Done criteria:** Python test suite is green. ✅

---

### Day 2 — Real LUT Extraction + Wire Style Worker into Temporal

**Morning (Saksham)**

Branch: `feat/sprint-d02-real-lut-and-style-worker`

1. **Replace simplified Reinhard with HM-MVGD-HM.**

   File: `services/style-worker/src/style_worker/lut_extract.py`

   The current code builds an identity LUT and applies mean/std transfer. Replace with `color-matcher` library:
   ```python
   from color_matcher import ColorMatcher
   from color_matcher.io_handler import load_img, save_img
   import numpy as np

   def extract_lut_from_reference(video_path: str, output_cube_path: str, size: int = 33):
       frames = sample_frames(video_path, n=50)
       if not frames:
           raise ValueError("No frames sampled")

       # Build reference "look" from median frame
       ref_frame = np.median(frames, axis=0).astype(np.uint8)

       # Build identity LUT as an image of shape (size*size, size*size, 3)
       # so color-matcher can apply the transfer
       identity_lut_img = _build_identity_lut_image(size)

       matcher = ColorMatcher(src=identity_lut_img, ref=ref_frame, method="hm-mvgd-hm")
       matched_lut_img = matcher.main()

       # Sample matched image back into .cube format
       lut_data = _image_to_cube_lut(matched_lut_img, size)
       _write_cube(output_cube_path, size, lut_data)
       return output_cube_path

   def _build_identity_lut_image(size: int) -> np.ndarray:
       b, g, r = np.meshgrid(
           np.linspace(0, 255, size, dtype=np.uint8),
           np.linspace(0, 255, size, dtype=np.uint8),
           np.linspace(0, 255, size, dtype=np.uint8),
           indexing="ij",
       )
       lut = np.stack([r, g, b], axis=-1)  # (size, size, size, 3)
       # Unfold to 2D image (size*size, size, 3)
       return lut.reshape(size * size, size, 3)

   def _image_to_cube_lut(img: np.ndarray, size: int) -> np.ndarray:
       # img is (size*size, size, 3); reshape back to cube
       return img.reshape(size, size, size, 3)

   def _write_cube(path: str, size: int, lut: np.ndarray):
       with open(path, "w") as f:
           f.write("TITLE \"Generated by AI Video Editor\"\n")
           f.write(f"LUT_3D_SIZE {size}\n")
           f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
           f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
           for z in range(size):
               for y in range(size):
                   for x in range(size):
                       r, g, b = lut[z, y, x] / 255.0
                       f.write(f"{r:.6f} {g:.6f} {b:.6f}\n")
   ```

   Add `color-matcher>=0.6.0` to `services/style-worker/pyproject.toml`.

2. **Add unit test** `services/style-worker/tests/test_lut_quality.py`:
   - Generate synthetic reference with orange/teal palette.
   - Extract LUT.
   - Apply LUT to a grayscale test pattern via FFmpeg.
   - Assert dominant output color shifts toward orange/teal via histogram check.

**Afternoon (Saksham)**

3. **Create Temporal workflow/activities for `style-worker`.**

   New file: `services/style-worker/src/style_worker/activities.py`
   ```python
   from temporalio import activity
   from .lut_extract import extract_lut_from_reference
   from .style_analysis import analyze_reference_style
   from .camera_motion import analyze_camera_motion
   from .text_extract import extract_text_overlays
   from .models import ReferenceStyleAnalysis

   @activity.defn
   async def analyze_reference_style_activity(input: dict) -> dict:
       video_path = input["video_path"]
       style = analyze_reference_style(video_path)
       motions = analyze_camera_motion(video_path)
       overlays = extract_text_overlays(video_path)
       return {
           "palette": style.palette,
           "contrast": style.contrast,
           "saturation": style.saturation,
           "brightness": style.brightness,
           "camera_motions": motions[:10],
           "detected_overlays": [o.model_dump() for o in overlays[:10]],
       }

   @activity.defn
   async def extract_lut_activity(input: dict) -> dict:
       video_path = input["video_path"]
       output_path = input["output_cube_path"]
       extract_lut_from_reference(video_path, output_path)
       return {"lut_path": output_path}
   ```

   New file: `services/style-worker/src/style_worker/workflows.py`
   ```python
   from temporalio import workflow
   from datetime import timedelta
   from .activities import analyze_reference_style_activity, extract_lut_activity

   @workflow.defn
   class ReferenceStyleWorkflow:
       @workflow.run
       async def run(self, input: dict) -> dict:
           style = await workflow.execute_activity(
               analyze_reference_style_activity,
               input,
               start_to_close_timeout=timedelta(minutes=2),
           )
           lut = await workflow.execute_activity(
               extract_lut_activity,
               input,
               start_to_close_timeout=timedelta(minutes=3),
           )
           return {"style": style, "lut": lut}
   ```

4. **Wire the workflow into the API.** In `apps/api/src/services/temporal.ts`, add `startReferenceStyleWorkflow(projectId, referenceAssetId)` and call it from upload completion when a reference asset is attached.

**EOD verify**

```bash
.venv/Scripts/python -m pytest services/style-worker/tests/test_lut_quality.py -v
# Run a real reference video through the new workflow:
# Expected: .cube file created and colors visibly shifted
```

**Done criteria:** Orange-palette reference produces a `.cube` LUT whose application visibly shifts a gray-card test pattern toward orange.

**Pitfall:** `color-matcher`'s `main()` returns a transformed image, not a LUT. You must build an identity LUT image, run the matcher on it, then sample back to `.cube` format (as shown above).

---

### Day 3 — AI Populates Effects + Overlays (The Prompt Rewrite)

**Branch:** `feat/sprint-d03-ai-populates-effects`

This is the single highest-leverage change for demo quality. Current AI prompts produce slots with empty `effects=[]` and empty `overlays=[]`. We teach it to fill them in.

**Files to modify**

- `services/shared-py/src/shared_py/ai_providers/base.py` — rewrite `SYSTEM_PROMPT_CUTLIST` and `_build_cutlist_context`.
- `services/reason-worker/src/reason_worker/cutlist_gen.py` — extend `CUTLIST_SCHEMA` to include `slot.effects[]` and `cutList.overlays[]`.
- `services/reason-worker/src/reason_worker/cutlist_gen.py:generate_cutlist_programmatic` — populate effects on high-energy beats so programmatic fallback also looks good.

**New `SYSTEM_PROMPT_CUTLIST`:**

```python
SYSTEM_PROMPT_CUTLIST = """You are a senior video editor AI for a beat-synced reels editor. You generate precise, beat-aligned cut-lists that include camera motion suggestions, text overlays, and effects.

OUTPUT: Valid JSON matching the provided schema EXACTLY. camelCase keys only. No prose.

CUT RHYTHM:
- Every slot.startS must equal a value in beatGrid.beats (snap to beat).
- Every 4-8 cuts, force a slot to start on a downbeat with duration >= 1.5s (breathing room).
- Total slots: aim for total_duration / avg_beat_period, but cap at 30 slots.

SHOT SELECTION:
- Map energyLevel to shot scale: <0.3 → wide/establishing; 0.3-0.6 → medium; 0.6-0.8 → medium_close_up; >0.8 → close_up.
- Use available_shot_types ONLY (do not request shot types the user doesn't have).
- If sectionLabel changes, force shot scale change.

CAMERA MOTION (motionHint):
- Read reference_analysis.camera_motions — if reference uses pan_left, slow_push, etc., echo that vocabulary.
- Low energy: static, slow_push, slow_pull.
- Medium energy: pan_left, pan_right, tilt_up.
- High energy: fast_push, zoom_in, whip, handheld, gimbal.

EFFECTS (populate slot.effects[]):
- On EVERY downbeat with energyLevel > 0.7: add zoom_punch_in (targetScale 1.15-1.3, durationMs 200-300, easing easeOut), startS = slot.startS.
- On EVERY slot with energyLevel < 0.4 and durationS > 1.5: optionally add focus_pull (targetBlur 0→8, durationMs 600-1000, easing easeInOut).
- On section boundaries (intro→verse, verse→chorus): add film_grain (intensity 0.15) for entire slot.
- On highest-energy slot in the song: add vignette (intensity 0.4).
- Do NOT stack > 2 effects per slot (it gets noisy).

TRANSITIONS:
- transitionOut = hard_cut for 80% of slots (clean, punchy).
- transitionOut = flash for slots that end a section boundary AND energyLevel > 0.7.
- transitionOut = dissolve only for the LAST slot of the outro (graceful exit).
- transitionOut = whip for slots ending a high-energy section that transitions to a lower-energy one.
- transitionOut = circle_open or wipe_left for slots in a montage (3+ rapid cuts of same shot type).
- Never use transitionOut = fade except in the final slot.

TEXT OVERLAYS (populate cutList.overlays[]):
- Read reference_analysis.detected_overlays — if reference has text at intro/section starts, echo the PATTERN (not the exact text).
- If no detected_overlays, add 1-2 default overlays:
  - At intro (startS=0, endS=2): a 2-3 word hook ("WATCH THIS" or song-themed). animation=fade_up.
  - At chorus/drop (startS=section.start, endS=section.start+1.5): a punctuation word ("DROP" or "GO"). animation=pop.
- position=center for hooks, position=bottom for context. fontSizePx=72 for hooks, 48 for context.
- color=#FFFFFF, stroke=#000000.

CONSISTENCY:
- If reference is fast-cut (avg shot < 1.2s), make user cut-list fast-cut too.
- If reference is contemplative (avg shot > 3s), make user cut-list slow.
- If reference has many text overlays, add 3-5 overlays to user output.
- If reference is "ad-style" (kinetic typography + zooms + whip cuts), match it.

VALIDATION:
- All slot.startS values must be in beatGrid.beats.
- Sum of all slot.durationS must equal totalDurationS (within 0.1s tolerance).
- All slot.selectedClipId references must be null (clip selection happens AFTER you return).
- All slot.effects[i].startS must be within [slot.startS, slot.startS + slot.durationS].
"""
```

**Extended schema in `cutlist_gen.py:CUTLIST_SCHEMA`:**

```python
"effects": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": [
                "zoom_punch_in", "focus_pull", "freeze_frame", "speed_ramp",
                "shake", "glitch", "vignette", "film_grain", "color_pop",
                "text_kinetic", "lower_third", "callout_arrow",
                "whoosh_sfx", "ding_sfx", "record_scratch_sfx"
            ]},
            "startS": {"type": "number"},
            "durationS": {"type": "number"},
            "params": {"type": "object"}
        },
        "required": ["type", "startS", "durationS", "params"]
    }
}
# Add "effects" to slot.required.
```

**Context builder enrichment** in `base.py:_build_cutlist_context`:

```python
lines.extend([
    "",
    "## Detected Text Overlays (from PaddleOCR on reference)",
])
for ov in style_analysis.get("detected_overlays", []):
    lines.append(f"- At {ov['start_s']:.2f}s: '{ov['text'][:50]}' position={ov['position']}")

lines.extend([
    "",
    "## Detected Camera Motions (per shot in reference)",
])
for i, motion in enumerate(style_analysis.get("camera_motions", [])[:10]):
    lines.append(f"- Shot {i+1}: {motion}")
```

**Programmatic fallback enrichment** in `cutlist_gen.py:generate_cutlist_programmatic`:

```python
effects = []
if is_downbeat and energy > 0.7:
    effects.append({
        "type": "zoom_punch_in",
        "startS": beat_time,
        "durationS": 0.3,
        "params": {"targetScale": 1.25, "durationMs": 300, "easing": "easeOut"}
    })
elif energy < 0.4 and duration > 1.5:
    effects.append({
        "type": "focus_pull",
        "startS": beat_time,
        "durationS": min(1.0, duration * 0.7),
        "params": {"targetBlur": 6.0, "durationMs": 800, "easing": "easeInOut"}
    })
if section != last_section:
    effects.append({
        "type": "film_grain",
        "startS": beat_time,
        "durationS": duration,
        "params": {"intensity": 0.15}
    })
slots[-1]["effects"] = effects
```

After all slots, add default overlays for intro and peak section.

**EOD verify**

```bash
pnpm e2e:pipeline:headless
# Inspect cut list: jq '.slots[].effects' on persisted cut list
# Expect: at least 3 slots with non-empty effects[]
# Expect: at least 1 overlay
```

**Done criteria:**
- Programmatic fallback produces ≥3 effects per generated cut list.
- AI fallback (Groq/Claude) produces ≥3 effects when reference is non-trivial.
- Overlays array has ≥1 entry.

**Pitfall:** JSON schema with `effects.params` as a generic object may make Groq emit malformed params. Add a one-retry-with-hint loop: if schema validation fails on params, re-prompt with "params must match the type's schema, e.g., zoom_punch_in requires targetScale + durationMs + easing."

---

### Day 4 — Render Missing Effects + Fix Transitions + Respect slot.start_s

**Branch:** `feat/sprint-d04-effects-renderer`

The AI now populates `effects[]`, but the compiler only handles 4 of 15 effect types. Add the rest and fix core bugs.

**Files to modify**

- `services/render-worker/src/render_worker/compiler.py` — extend `_apply_video_effects` + `XFADE_MAP` + segment extraction.

**1. Fix `-ss 0` bug.** In `compiler.py` segment extraction, change:

```python
# OLD (line ~207):
# -ss 0 -t {duration}

# NEW:
start = max(0.0, slot.start_s)
end = start + duration + transition_pad
# Clamp end to clip duration at runtime via probe data
segment_cmd = [
    "ffmpeg", "-y", "-ss", str(start), "-t", str(duration + transition_pad),
    "-i", clip_path,
    # ... rest of filter
]
```

Add validation that `slot.start_s + slot.duration_s <= clip_duration`.

**2. Implement missing effects in `_apply_video_effects`:**

```python
elif etype == "focus_pull":
    target_blur = params.get("targetBlur", 6.0)
    dur = params.get("durationMs", 800) / 1000.0
    # Approximate focus pull: ramp gblur sigma over duration
    filters.append(
        f"gblur=sigma='if(lte(t,{dur}),{target_blur}*t/{dur},{target_blur})':enable='lte(t,{dur*1.5})'"
    )

elif etype == "freeze_frame":
    hold = params.get("holdMs", 500) / 1000.0
    filters.append(f"tpad=start_mode=clone:start_duration={hold}")

elif etype == "speed_ramp":
    start_speed = params.get("startSpeed", 1.0)
    end_speed = params.get("endSpeed", 2.0)
    filters.append(
        f"setpts='PTS / ({start_speed} + ({end_speed}-{start_speed})*(T/{max(dur, 0.001)}))'"
    )

elif etype == "color_pop":
    hue = params.get("hueShift", 0.0)
    sat = params.get("saturation", 1.5)
    filters.append(f"hue=h={hue}:s={sat}")

elif etype == "glitch":
    intensity = params.get("intensity", 0.3)
    dur = params.get("durationMs", 200) / 1000.0
    filters.append(
        f"noise=c0s={intensity*20}:allf=t+u,"
        f"hue=h='5*sin(t*30)':enable='lte(t,{dur})'"
    )
```

**3. Fix `XFADE_MAP`:**

```python
XFADE_MAP = {
    "fade": "fade",
    "dissolve": "dissolve",  # real dissolve in FFmpeg >= 4.3
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "wipe_up": "wipeup",
    "wipe_down": "wipedown",
    "circle_open": "circleopen",
    "circle_close": "circleclose",
    "slide_up": "slideup",
    "slide_down": "slidedown",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "pixelize": "pixelize",
    "hlslice": "hlslice",
    "vlslice": "vlslice",
    "flash": "fadewhite",  # real white-frame flash in FFmpeg >= 4.3
    "fadeblack": "fadeblack",
    "whip": "hlslice",
    "smoothleft": "smoothleft",
    "smoothright": "smoothright",
    "diagtl": "diagtl",
    "diagtr": "diagtr",
}
```

Verify runtime FFmpeg version supports `fadewhite` and `dissolve` (FFmpeg ≥ 4.3). If the runtime is older, document upgrade in deployment docs.

**4. Kinetic text animations in text overlay renderer.**

Update `compile_timeline` text overlay loop:

```python
anim = overlay.animation or "none"
enable_expr = f"between(t\\,{overlay.start_s}\\,{overlay.end_s})"
alpha_expr = "1"
extra_y = ""
font_expr = str(overlay.font_size_px)

if anim == "fade_up":
    alpha_expr = f"min((t-{overlay.start_s})/0.4\\,1)"
    extra_y = f"+30*(1-min((t-{overlay.start_s})/0.4\\,1))"
elif anim == "typewriter":
    alpha_expr = f"min((t-{overlay.start_s})/0.6\\,1)"
elif anim == "pop":
    alpha_expr = f"min((t-{overlay.start_s})/0.2\\,1)"
    # Fallback if fontsize_expr unsupported
    font_expr = f"{overlay.font_size_px} * (0.5 + 0.5*min((t-{overlay.start_s})/0.2\\,1))"
elif anim == "slide_left":
    x_expr = f"w + (-(w-text_w)/2 - w) * min((t-{overlay.start_s})/0.4\\,1)"
```

**EOD verify**

```bash
.venv/Scripts/python -m pytest services/render-worker/tests/test_render_compiler.py -v
# Manually render a project with focus_pull and inspect output.
```

**Done criteria:** Every effect type in the enum renders without crashing; manual eyeball check confirms focus_pull blurs in.

**Pitfall:** FFmpeg `gblur` doesn't have built-in time animation. Real focus pull requires crossfading between sharp and blurred copies of the slot. The enable-based approximation is acceptable for demo; document the v2 fix.

---

### Day 5 — Twelve Labs Marengo 3.0 + SigLIP-2 Local Fallback

**Branch:** `feat/sprint-d05-clip-understanding`

Replace the 0.7 placeholder with real semantic clip ranking.

**Files to create**

- `services/shared-py/src/shared_py/clip_embedding.py` — Twelve Labs client.
- `services/style-worker/src/style_worker/siglip2.py` — local SigLIP-2 fallback.
- `services/reason-worker/src/reason_worker/clip_embed.py` — orchestrator.

**Files to modify**

- `services/reason-worker/src/reason_worker/clip_rank.py` — accept embeddings, compute cosine.
- `services/reason-worker/src/reason_worker/orchestrator.py` — call embed before rank.
- `services/shared-py/src/shared_py/config.py` — add Twelve Labs init.

**Twelve Labs client implementation:**

```python
# services/shared-py/src/shared_py/clip_embedding.py
import os
import httpx
import numpy as np
from typing import Optional, List

TWELVELABS_BASE = "https://api.twelvelabs.io/v1.3"

class TwelveLabsClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TWELVELABS_API_KEY")
        if not self.api_key:
            raise ValueError("TWELVELABS_API_KEY not set")
        self.client = httpx.Client(
            base_url=TWELVELABS_BASE,
            headers={"x-api-key": self.api_key},
            timeout=60.0,
        )

    def create_index(self, name: str) -> str:
        res = self.client.post("/indexes", json={
            "index_name": name,
            "models": [{"model_name": "marengo3.0", "model_options": ["visual", "audio"]}]
        })
        res.raise_for_status()
        return res.json()["_id"]

    def index_video(self, index_id: str, video_url: str) -> str:
        res = self.client.post("/tasks", json={
            "index_id": index_id,
            "video_url": video_url,
        })
        res.raise_for_status()
        return res.json()["_id"]

    def wait_for_task(self, task_id: str, max_wait_s: int = 300) -> str:
        import time
        start = time.time()
        while time.time() - start < max_wait_s:
            res = self.client.get(f"/tasks/{task_id}")
            res.raise_for_status()
            data = res.json()
            if data["status"] == "ready":
                return data["video_id"]
            if data["status"] == "failed":
                raise RuntimeError(f"Indexing failed: {data}")
            time.sleep(5)
        raise TimeoutError(f"Indexing didn't complete in {max_wait_s}s")

    def get_embedding(self, video_id: str) -> np.ndarray:
        res = self.client.get(f"/embeddings/{video_id}")
        res.raise_for_status()
        segments = res.json()["video_embedding"]["segments"]
        vectors = [np.array(s["embeddings_float"]) for s in segments if s.get("embedding_scope") == "clip"]
        if not vectors:
            return np.zeros(1024)
        return np.mean(vectors, axis=0)

    def embed_text(self, text: str) -> np.ndarray:
        res = self.client.post("/embed", json={"model_name": "marengo3.0", "text": text})
        res.raise_for_status()
        return np.array(res.json()["text_embedding"]["segments"][0]["embeddings_float"])

    def search(self, index_id: str, query_text: str, top_k: int = 5) -> List[dict]:
        res = self.client.post("/search", json={
            "index_id": index_id,
            "search_options": ["visual", "audio"],
            "query_text": query_text,
            "page_limit": top_k,
        })
        res.raise_for_status()
        return res.json()["data"]
```

**SigLIP-2 local fallback:**

```python
# services/style-worker/src/style_worker/siglip2.py
import os
import torch
from transformers import AutoModel, AutoProcessor
import numpy as np
import cv2

MODEL_NAME = "google/siglip2-base-patch16-256"
_model = None
_processor = None

def _load():
    global _model, _processor
    if _model is None:
        _model = AutoModel.from_pretrained(MODEL_NAME)
        _processor = AutoProcessor.from_pretrained(MODEL_NAME)
        _model.eval()
    return _model, _processor

def embed_video_frames(video_path: str, n_frames: int = 8) -> np.ndarray:
    model, processor = _load()
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = np.linspace(0, max(total - 1, 0), n_frames, dtype=int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(rgb)
    cap.release()
    if not frames:
        return np.zeros(768)
    inputs = processor(images=frames, return_tensors="pt")
    with torch.no_grad():
        outputs = model.get_image_features(**inputs)
    return outputs.detach().numpy().mean(axis=0)

def embed_text(text: str) -> np.ndarray:
    model, processor = _load()
    inputs = processor(text=[text], padding="max_length", return_tensors="pt")
    with torch.no_grad():
        outputs = model.get_text_features(**inputs)
    return outputs.detach().numpy()[0]
```

**Embed orchestrator:**

```python
# services/reason-worker/src/reason_worker/clip_embed.py
import os
from typing import Dict, List
import numpy as np
from shared_py.clip_embedding import TwelveLabsClient
from style_worker.siglip2 import embed_video_frames, embed_text as siglip_text

USE_TWELVELABS = bool(os.environ.get("TWELVELABS_API_KEY"))

def embed_user_clips(project_id: str, clip_assets: List[dict]) -> Dict[str, np.ndarray]:
    if USE_TWELVELABS:
        return _embed_marengo(project_id, clip_assets)
    return {a["id"]: embed_video_frames(a["local_path"], n_frames=8) for a in clip_assets}

def _embed_marengo(project_id, clip_assets):
    client = TwelveLabsClient()
    index_id = client.create_index(f"project-{project_id}")
    embeddings = {}
    for asset in clip_assets:
        try:
            task_id = client.index_video(index_id, asset["storage_url"])
            video_id = client.wait_for_task(task_id, max_wait_s=300)
            embeddings[asset["id"]] = client.get_embedding(video_id)
        except Exception:
            embeddings[asset["id"]] = embed_video_frames(asset["local_path"], n_frames=8)
    return embeddings

def embed_slot_query(text: str, use_twelve: bool = USE_TWELVELABS):
    if use_twelve:
        try:
            return TwelveLabsClient().embed_text(text)
        except Exception:
            pass
    return siglip_text(text)
```

**Fix `clip_rank.py`:**

```python
# Replace the stubbed 0.7 block with:
if embeddings and clip_id in embeddings and slot_embedding is not None:
    emb = embeddings[clip_id]
    norm_emb = np.linalg.norm(emb)
    norm_slot = np.linalg.norm(slot_embedding)
    if norm_emb > 0 and norm_slot > 0:
        cosine = float(np.dot(emb, slot_embedding) / (norm_emb * norm_slot))
        semantic = (cosine + 1) / 2  # -1..1 -> 0..1
    else:
        semantic = 0.5
else:
    semantic = 0.5
```

**EOD verify**

```bash
# Set TWELVELABS_API_KEY and run pipeline with 5 distinctly different clips
# Expect: semantic scores vary; top-ranked clip per slot is sensibly chosen
```

**Done criteria:**
- With Twelve Labs key: semantic scores vary (not all 0.7).
- Without key: pipeline doesn't crash (SigLIP-2 fallback).

**Pitfall:** Twelve Labs indexing is slow (30–120 s per clip). Cache embeddings in Redis with key `clip_embedding:{asset_id}`. Add a budget check: if total clip duration > 5 min, fall back to SigLIP-2.

---

### Day 6 — Pexels Stock Footage + Audio Ducking + ElevenLabs SFX

**Branch:** `feat/sprint-d06-stock-audio-sfx`

Three independent additions that make the editor feel complete.

**6a. Pexels stock footage fallback**

When AI generates N slots and user has fewer clips, fill the gap. Priority:
1. Reuse user clips with freeze_frame or speed_ramp.
2. Pexels stock query based on `slot.subjectHint` + `slot.targetShotType`.
3. Last resort: black frame + overlay.

New file: `services/reason-worker/src/reason_worker/stock_fallback.py`

```python
import os
import httpx
from typing import List, Dict

PEXELS_KEY = os.environ.get("PEXELS_API_KEY")

def query_pexels(query: str, top_k: int = 3) -> List[Dict]:
    if not PEXELS_KEY:
        return []
    res = httpx.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "per_page": top_k, "orientation": "portrait"},
        headers={"Authorization": PEXELS_KEY},
        timeout=10,
    )
    if res.status_code != 200:
        return []
    results = []
    for v in res.json().get("videos", []):
        files = sorted(
            [f for f in v["video_files"] if f.get("quality") == "sd"],
            key=lambda f: f.get("width", 0)
        )
        if files:
            results.append({
                "url": files[0]["link"],
                "duration_s": v["duration"],
                "width": files[0]["width"],
                "height": files[0]["height"],
            })
    return results

def fill_empty_slots(slots, selected_clips: Dict[int, str], user_clip_count: int) -> Dict[int, Dict]:
    fills = {}
    for slot in slots:
        if slot.index in selected_clips:
            continue
        if user_clip_count > 0:
            fills[slot.index] = {"strategy": "reuse", "speed_ramp": slot.duration_s / 5.0}
            continue
        results = query_pexels(f"{slot.subject_hint} {slot.target_shot_type}")
        if results:
            fills[slot.index] = {"strategy": "stock", "url": results[0]["url"]}
            continue
        fills[slot.index] = {"strategy": "black", "text": "•"}
    return fills
```

Compiler integration: when `clip_path` missing, apply fill strategy.

**6b. Audio ducking (sidechain compression)**

Modify `compiler.py:_build_audio_filter`:

```python
def _build_audio_filter(audio_tracks, base_input_count):
    # ... existing setup ...
    voiceover_idx = next((i for i, t in enumerate(audio_tracks) if getattr(t, "is_voiceover", False)), None)
    music_idx = next((i for i, t in enumerate(audio_tracks) if getattr(t, "is_music", False)), None)

    if voiceover_idx is not None and music_idx is not None:
        v = base_input_count + voiceover_idx
        m = base_input_count + music_idx
        parts.append(
            f"[a{v}][a{m}]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300[ducked_music];"
            f"[a{v}][ducked_music]amix=inputs=2:duration=longest:normalize=0[amixed]"
        )
        return ";".join(parts), "[amixed]"
    # fallback amix ...
```

Add `is_voiceover: bool = False` and `is_music: bool = False` to `AudioTrack` model.

**6c. ElevenLabs SFX on dramatic transitions**

New file: `services/render-worker/src/render_worker/sfx.py`

```python
import os
import httpx
from pathlib import Path
import hashlib

ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY")
SFX_CACHE = Path("/tmp/sfx_cache")
SFX_CACHE.mkdir(exist_ok=True)

SFX_FOR_TRANSITION = {
    "flash": "short bright whoosh, ascending",
    "whip": "fast whip sound effect, single hit",
    "dissolve": "soft impact swell",
}

def get_sfx(prompt: str, duration_s: float = 0.6) -> str:
    cache_key = hashlib.sha256(f"{prompt}:{duration_s}".encode()).hexdigest()[:16]
    cache_path = SFX_CACHE / f"{cache_key}.mp3"
    if cache_path.exists():
        return str(cache_path)
    if not ELEVENLABS_KEY:
        return ""
    res = httpx.post(
        "https://api.elevenlabs.io/v1/sound-generation",
        headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
        json={"text": prompt, "duration_seconds": duration_s, "prompt_influence": 0.7},
        timeout=30,
    )
    if res.status_code == 200:
        cache_path.write_bytes(res.content)
        return str(cache_path)
    return ""

def get_transition_sfx(transition_type: str) -> str:
    prompt = SFX_FOR_TRANSITION.get(transition_type)
    return get_sfx(prompt, duration_s=0.6) if prompt else ""
```

Compiler integration: for each dramatic transition, fetch SFX and mix it into the audio filter at the correct offset.

**EOD verify**

```bash
# Upload 2 user clips, force 8 slots → no black holes
# Render with voiceover → music ducks under voice
# Render with flash transition → whoosh audible
```

**Done criteria:**
- Pipeline never produces black holes given ≥1 user clip.
- Music ducks under voiceover.
- Whoosh audible at flash transitions.

**Pitfall:** Pexels videos may differ in aspect ratio. Force-crop with `scale=W:H:force_original_aspect_ratio=increase,crop=W:H` during segment extraction.

---

### Day 7 — Render Preview UI Button + Prompt Edit Diff

**Branch:** `feat/sprint-d07-preview-and-diff`

**7a. Render preview UI button**

`render_preview()` already exists in `compiler.py:344`. Wire it to UI.

New backend route in `apps/api/src/routes/renders.ts`:

```typescript
app.post("/:projectId/render-preview", async (request, reply) => {
  // ownership check
  const workflowId = await startTemporalWorkflow("render_preview_workflow", { projectId });
  return { workflowId, status: "started" };
});
```

New workflow in `services/render-worker/src/render_worker/workflows.py`:

```python
@workflow.defn
class RenderPreviewWorkflow:
    @workflow.run
    async def run(self, input: dict) -> str:
        return await workflow.execute_activity(
            render_preview_activity,
            input,
            start_to_close_timeout=timedelta(minutes=2),
        )
```

Frontend: `apps/web/src/components/editor/RenderPreviewButton.tsx`.

**7b. Prompt edit diff visualization**

New file: `apps/web/src/lib/cutlistDiff.ts`

```typescript
import { compare, Operation } from "fast-json-patch";
import type { CutList } from "@ai-video-editor/shared-types";

export function diffCutLists(before: CutList, after: CutList): Operation[] {
  return compare(before as object, after as object);
}

export function summarizeDiff(ops: Operation[]): string {
  const adds = ops.filter(o => o.op === "add").length;
  const removes = ops.filter(o => o.op === "remove").length;
  const replaces = ops.filter(o => o.op === "replace").length;
  return `${adds} added · ${removes} removed · ${replaces} changed`;
}
```

Integrate in `PromptPanel.tsx`:

```typescript
async function applyPrompt() {
  const before = cutList;
  const res = await api.projects.prompt(projectId, promptText);
  const ops = diffCutLists(before, res.cutList);
  toast.success(`Applied: ${summarizeDiff(ops)}`, {
    action: { label: "Undo", onClick: () => dispatch({ type: "set_cutlist", payload: before }) },
    duration: 10000,
  });
}
```

**EOD verify:** Click preview → 360p MP4 plays within 90s. Type prompt → diff toast appears, Undo works.

---

### Day 8 — Closed-Loop Prompt Edit + Sample Attachment

**Branch:** `feat/sprint-d08-closed-loop-prompt`

The prompt edit pipeline (`ai.ts:applyPromptEdit`) works, but we need closed-loop quality: apply → preview → show result.

**Flow:**

1. User types prompt.
2. Backend calls LLM with current cutlist + reference analysis + attached sample (if any).
3. Returns JSON Patch + natural-language explanation.
4. Frontend applies patch, shows diff, triggers preview render.
5. Preview plays; user can Undo or Render Full.

**Sample attachment:**

- Add `attachedAssetId` to prompt schema (verify it exists; if not, add it).
- Add `prompt_sample` to `ASSET_TYPE` enum and DB CHECK constraint.
- UI: paperclip button in `PromptPanel.tsx`.
- Backend: when `attachedAssetId` present, quick-probe the sample for camera motion + transitions and include in prompt context.
- Cleanup: delete `prompt_sample` asset after apply.

**Prompt context enrichment for sample:**

```typescript
if (attachedAssetId) {
  const sampleAsset = await db.query.assets.findFirst({ where: eq(assets.id, attachedAssetId) });
  const sampleAnalysis = await quickProbeSample(sampleAsset);
  context += `\n## Attached Sample Analysis\n${formatSampleAnalysis(sampleAnalysis)}`;
}
```

**EOD verify:** Attach a whip-pan video, type "use this motion style" → AI returns cutlist with `motion_hint: whip` slots.

---

### Day 9 — Voiceover Transcription + Dynamic Subtitles

**Branch:** `feat/sprint-d09-subtitles`

`POST /api/projects/:id/transcribe` already uses Whisper. Auto-transcribe and generate subtitle overlays.

1. Add `autoTranscribe` flag to project creation.
2. After transcription, split long Whisper segments into ≤6-word chunks.
3. Populate `cutList.overlays` with styled captions.

```python
for seg in whisper_segments:
    words = seg.text.split()
    chunk_size = 6
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i+chunk_size])
        start = seg.start + (i / len(words)) * (seg.end - seg.start)
        end = seg.start + ((i + chunk_size) / len(words)) * (seg.end - seg.start)
        overlay = Overlay(
            text=chunk,
            start_s=start,
            end_s=end,
            position="bottom",
            font_size_px=48,
            animation="typewriter",
        )
        cutlist.overlays.append(overlay)
```

**EOD verify:** Upload a song with clear vocals → subtitles appear synced at bottom.

**Done criteria:** Auto-subtitles work for English audio.

---

### Day 10 — Style Tier UI + Admin Reset + Asset Model Cleanup

**Branch:** `feat/sprint-d10-ui-polish`

**10a. Visual style tier picker**

Replace dropdown with visual cards in `CreateProjectDialog.tsx`:

```typescript
const TIERS = [
  { id: "cuts_only", label: "Cuts Only", desc: "Just sync to the beat", icon: "✂️" },
  { id: "color_grade", label: "+ Color", desc: "Match reference palette", icon: "🎨" },
  { id: "with_text", label: "+ Text", desc: "Kinetic titles", icon: "📝" },
  { id: "with_effects", label: "+ Effects", desc: "Zooms, focus pulls", icon: "💫" },
  { id: "full_remix", label: "Full Remix", desc: "AI baseline + your control", icon: "🚀" },
];
```

**10b. Admin reset endpoint**

New route in `apps/api/src/routes/admin.ts`: `POST /admin/reset-user/:userId` wipes all projects/assets/renders for one user. This lets us reuse the same investor test account.

**10c. Asset model cleanup**

Add asset sub-types to `packages/shared-types/src/enums.ts`:
- `lut`, `style_analysis`, `beat_grid`, `transcription`, `stem_vocals`, `stem_music`, `filler_clip`, `generated_clip`, `prompt_sample`.

**EOD verify:** Tier picker renders correctly; reset endpoint clears demo account.

---

### Day 11 — Real-World Stress Test with 5 Diverse References

**Branch:** none (testing + fix branches as needed)

Devayan + Saksham pick 5 reference videos from very different aesthetics:

1. Apple ad — clean, slow, color-graded, minimal text.
2. TikTok dance — fast cuts, hand-held, no color grade.
3. Travel reel — drone shots, sunset palette, scene transitions.
4. Tech product demo — text-heavy, zoom punch-ins, ding SFX.
5. Indian wedding film — slow motion, warm grade, mood.

For each: source 3–5 matching clips. Run pipeline. Document in `docs/demo-test-log.md`:
- What works.
- What looks amateur.
- Top 5 bugs to fix tomorrow.

**EOD result:** `docs/demo-test-log.md` with screenshots, 1–10 scores, and the top 5 bugs.

---

### Day 12 — Fix Top 5 Bugs from Day 11

**Branch:** `feat/sprint-d12-demo-bugs`

Whatever they are. Anticipated failure modes:

| Bug | Fix |
|---|---|
| LUT washes out skin tones | Add `skin_tone_protection` param to LUT extraction |
| Stock footage clashes | Only use stock if user clips < 2; otherwise reuse |
| Subtitles too long | Auto-split sentences at clause boundaries |
| Whoosh SFX too loud | Drop SFX gain to -12 dB |
| Preview still >90s | Cap at 10s, lower resolution to 240p for preview |
| Transitions feel repetitive | Enforce transition variety rule in prompt |

**EOD verify:** All 5 references re-tested; scores improved.

---

### Day 13 — Demo Script + Rehearsal

**Branch:** `feat/sprint-d13-demo-script`

Write exact demo script and rehearse.

Create `docs/demo-script.md`:

```markdown
# Demo Script — 2026-07-05

### Opening
"We built an AI video editor that takes one reference video, your clips, and a song — and gives you a state-of-the-art edit."

### Step 1 — Upload reference
"Here's a reference video — say it's a Nike ad you saw and want yours to feel like."
[Upload reference.mp4]

### Step 2 — Upload clips + song
"Drop in your own clips and your song."
[Upload clip1.mp4, clip2.mp4, clip3.mp4, song.mp3]

### Step 3 — Select tier
"Pick the level of AI involvement — from just cuts to full remix."
[Click with_effects card]

### Step 4 — Preview
"In under 90 seconds, you get a preview."
[Click Preview button]

### Step 5 — Show preview
[Point at color grade, zoom punch-ins, text overlays]

### Step 6 — Prompt edit
"Want to refine? Talk to it: 'Make the cut at 0:14 land on the snare and add a focus pull when she enters frame.'"
[Type prompt, click Apply]

### Step 7 — Diff + Undo
"Every change is explainable and reversible."
[Show diff toast, click Undo, then re-apply]

### Step 8 — Render full
"Full 720p render in under 5 minutes."
[Click Render Full]

### Close
"Next: we add motion graphics, multi-track timeline, and the cinematic grade pipeline using SAM and Gaussian Splatting."
```

Add fallback plans for each step.

Rehearse with Saksham as the "investor."

---

### Day 14 — Final Dry Run + Deploy Lockdown

**Morning:** Full dry run from scratch (new browser, fresh DB) following the script.
**Afternoon:** Fix anything broken; verify all 5 references still produce good output.
**EOD:** Deploy lockdown — no merges after 17:00 IST.

Sleep. Demo at the scheduled investor meeting.


---

## 6. APIs to Wire — Single Reference Sheet

| API | Env var | Required for | Backup |
|---|---|---|---|
| Twelve Labs Marengo 3.0 | `TWELVELABS_API_KEY` | Semantic clip ranking | SigLIP-2 local |
| ElevenLabs SFX | `ELEVENLABS_API_KEY` | Whoosh / ding / scratch | Silent (no SFX) |
| Pexels Video | `PEXELS_API_KEY` | Filler clips | Reuse user clips + speed_ramp |
| OpenAI Whisper | `OPENAI_API_KEY` | Voiceover subtitles | Skip subtitles |
| Anthropic Claude | `ANTHROPIC_API_KEY` | Prompt edit (high quality) | Groq fallback |
| Groq (Llama / Mixtral) | `GROQ_API_KEY` | Cut list generation (default) | Claude fallback |
| Google Gemini | `GOOGLE_API_KEY` | Tertiary AI fallback | Programmatic generator |
| Cloudflare R2 | `R2_*` | Storage | MinIO local |
| Clerk | `CLERK_SECRET_KEY` | Auth | `DISABLE_CLERK_AUTH=1` for E2E |

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Twelve Labs API down or slow on demo day | Med | High | SigLIP-2 fallback is silent + automatic. Pre-cache embeddings for canned demo clips. |
| Investor's reference video is unusual (cartoon, b&w, extreme aspect ratio) | Med | Med | Test Day 11 with diverse refs. LUT extraction has identity fallback. |
| Render time > 5 min for investor's clips | Low | High | Preview button (Day 7) buys 90s. Full render runs in background. |
| AI prompt edit returns malformed JSON | Med | Med | Phase 1.2 already has 1-retry-with-hint; verify in Day 8. |
| Stock footage from Pexels looks amateur | Low | Med | Use HD-only filter; cap stock usage to 40% of slots. |
| ElevenLabs SFX takes >15s and demo feels slow | Low | Med | Pre-warm SFX cache on app startup. |
| Demo environment crashes (Docker, Temporal, MinIO) | Med | Catastrophic | Run dry runs on CLEAN environment Day 14. Have backup laptop ready. |
| Internet flaky at demo venue | Med | High | Pre-render 3 demo videos. Show those first, then live. |
| Saksham/Amitansu divergent priorities | Med | Med | Devayan shares this plan. Saksham owns Days 1–8 (quality); Amitansu owns Days 9–12 (UI/testing). |
| Slot `start_s` bug not fully fixed | Med | High | Day 4 is a blocker; add unit test that asserts `-ss` uses `slot.start_s`. |

---

## 8. Post-Demo Continuation

If the demo lands and Series A closes, resume in this order:

### 8.1 Immediate Post-Close (Weeks 1–2)

1. Merge all sprint branches to `main`.
2. Fix the remaining 9→0 test-failure backlog permanently.
3. Implement proper observability (Loki + Grafana + Sentry).
4. Add rate limiting and cost guards on Twelve Labs / generative APIs.
5. Ship the hardening plan (Section 9).

### 8.2 V1 Product (Months 1–3)

1. **Twelve Labs deep integration:** Marengo search, Pegasus summaries, classification.
2. **Stock footage expansion:** Pexels + Mixkit + Coverr + Pixabay.
3. **Audio intelligence:** Demucs stem separation, auto-ducking, AI SFX library, LUFS normalization.
4. **Captions & text:** Whisper transcription, auto-subtitles, kinetic templates, brand kits.
5. **Platform presets:** 9:16, 1:1, 4:5, 16:9 with one-click export.
6. **Subscription tiers:** Map `cuts_only` → `full_remix` to pricing plans.

### 8.3 V2 Category Leader (Months 3–12)

1. **Generative filler:** Seedance / Kling / Runway for missing shots.
2. **Object-aware editing:** SAM2 masks, isolate/replace objects.
3. **Style transfer:** Neural style transfer with temporal consistency.
4. **Motion transfer:** Extract camera path from reference and apply.
5. **Collaboration:** Comments, review links, shared workspaces.
6. **Mobile app / responsive capture-to-edit flow.

### 8.4 Research / "The GOOD SHIT" (Months 6–24)

Saksham's WhatsApp 5:13 AM list, in recommended order:

1. **SAM 2 for layer separation** — research phase: 4 weeks.
2. **3D Gaussian Splatting reconstruction** — research phase: 6 weeks.
3. **DROID-SLAM neural camera tracker** — research phase: 4 weeks.
4. **ControlNet neural lighting** — research phase: 3 weeks.
5. **VASE low-grade preview generation** — research phase: 2 weeks.
6. **Remotion-based timeline UI** — engineering phase: 8 weeks.
7. **Seedance cinematic generation with authenticity weights** — research phase: 6 weeks, **DO NOT RELEASE** per Saksham until proven.

**Estimated cinematic-grade editor:** 6 months engineering + research post-Series-A.

---

## 9. Hardening Plan Archive (Reference Only — Do Not Execute During Sprint)

The previous multi-pass hardening plan is paused. Key phases to resume after demo:

- Pass 1.4 — API error normalization.
- Pass 1.5 — Engineering quality baseline (TS strict + Biome + AGENTS.md).
- Pass 2 — Forms + optimistic UI.
- Pass 3 — Foot-gun elimination (R2 lifecycle, render queue, SSE, presence).
- Pass 4 — Observability + safety (LGTM + GlitchTip + guardrails).
- Pass 5 — Product vision: 5-tier ladder, effect library, multi-song, command palette.
- Pass 6 — Polish + repo hygiene.

**Do NOT touch any of these during the 14-day sprint.** Every minute spent on hardening is a minute not spent on demo-critical quality.

---

## 10. Daily Standup Template (Devayan, Each Morning)

```
Day N (date):
  Yesterday: <what shipped>
  Today: <what's planned per kimi_plans.md>
  Blockers: <API delays, env issues, design questions>
  Status: <on track / at risk / behind>
```

Share in WhatsApp with Saksham + Amitansu so the team stays synced.

---

## 11. Demo-Day Checklist (Day 14 EOD)

- [ ] All API keys live in production env.
- [ ] Demo project pre-seeded with 5 reference videos and matching clip sets.
- [ ] At least 3 successful end-to-end runs of each demo scenario.
- [ ] Backup recordings of the demo flow stored offline.
- [ ] Backup laptop ready with the entire stack running.
- [ ] Mobile hotspot available.
- [ ] `docs/demo-script.md` printed.
- [ ] Saksham briefed as backup presenter.
- [ ] Investor's content (if pre-shared) tested.
- [ ] Reset endpoint working — can clear demo account between calls.
- [ ] LUT extraction tested with NON-cinematic reference (e.g., selfie video) — must not crash.
- [ ] Prompt edit tested with adversarial input ("delete everything") — must safe-fail with `AI_REFUSED`.
- [ ] All Saksham/Amitansu WhatsApp follow-ups addressed.

---

## 12. Closing Note from the Planner

The demo question is not *"Can we build cinema-grade AI editing in 14 days?"* The answer is no.

The question is: *"Can we build the cleanest, most coherent single-track AI editor anyone has shipped, with the prompt-edit loop being the wow factor?"* **The answer is yes, with this plan.**

The differentiator vs Runway / Kling / Pika is that we edit **your footage with your clips**, not generate new pixels. That's a smaller bet but a more defensible market position for an India-based team competing on price + execution speed.

The cinematic generation Saksham described (SAM + 3D Gaussian Splatting + DROID-SLAM) is the right moat for v2. Don't let the investor talk you into building it pre-funding — point at the architecture diagram in Section 4 and say: *"This is what we ship after closing."*

Devayan: you've got this. The pipeline already runs. The hard parts — beat detection, FFmpeg orchestration, AI integration — are done. The next 14 days is **polish and wiring, not build from scratch.**

Good luck.

— Kimi Code CLI (2026-06-21)
