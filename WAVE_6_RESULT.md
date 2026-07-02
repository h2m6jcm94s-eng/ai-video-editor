# Wave 6 Result: Pro Edit Features (Part 1)

**Date:** 2026-07-02
**Branch:** `main`
**Commit:** `f6a5b8c`
**Scope:** Stabilization, auto-reframe, and text-based editing primitives.

## What changed

### Auto-reframe
- New `services/render-worker/src/render_worker/reframe.py`:
  - `parse_aspect_ratio(aspect)` parses strings like `9:16`, `16:9`, `1:1`.
  - `compute_reframe_crop(input_width, input_height, target_aspect, subject_box)` returns a center-crop rectangle matching the target aspect, optionally centering on a normalized subject bounding box.
  - `reframe_filter(video_path, target_aspect, subject_box)` probes the clip and returns an FFmpeg `crop=w:h:x:y` filter string.
- The render compiler already applies slot effects of type `reframe` via `_apply_video_effects`, so auto-reframe is exercised end-to-end once a slot carries the effect.

### Stabilization
- New `services/render-worker/src/render_worker/stabilize.py`:
  - `stabilization_filter(method)` returns `deshake=rx=64:ry=64:blocksize=8` (default) or a two-pass `vidstabdetect`/`vidstabtransform` chain.
  - `stabilize_clip(input_path, output_path, method)` runs FFmpeg and writes a stabilized intermediate clip.
  - `stabilization_available(method)` probes whether `ffmpeg` and (for `vidstab`) the libvidstab filters are present.
- The render compiler applies slot effects of type `stabilize` via `_apply_video_effects`.

### Text-based editing primitives
- New `services/reason-worker/src/reason_worker/text_edit.py`:
  - `parse_edit_command(command)` converts natural-language commands into typed `EditOperation`s.
    - Supported: `"cut from 0:05 to 0:10"`, `"remove 5.0-10.0"`, `"trim 1:00 to 1:30"`, `"remove overlays"`, `"remove captions"`, etc.
  - `apply_text_edits(cutlist, operations)` mutates the cutlist in place: removes/shortens slots inside cut regions and clears all overlays.
  - `_reindex_slots(cutlist)` renumbers remaining slots after edits.
- New `apply_text_edits_activity` in `services/reason-worker/src/reason_worker/activities.py` parses commands and applies them to a raw cutlist.
- Wired into `GenerateFromReferenceWorkflow` after `generate_cutlist_activity` when `options.textEdits` / `options.text_edits` is provided.
- Registered `apply_text_edits_activity` in `services/reason-worker/src/reason_worker/__main__.py`.

### Feature toggles
- Added to `AdaptiveFeatures` in `services/shared-py/src/shared_py/models.py`:
  - `use_stabilization`
  - `use_auto_reframe`
  - `use_text_based_edits`

### Reason cutlist generation
- `services/reason-worker/src/reason_worker/cutlist_gen.py` now tags slots with `Effect(type="reframe", params={"target_aspect": "9:16"})` when `use_auto_reframe` is enabled and `Effect(type="stabilize")` when `use_stabilization` is enabled.
- The compiler picks these effects up automatically through the existing effect-prefilter path.

### Tests
- `services/reason-worker/tests/test_text_edit.py`: 3 tests (parse commands, apply cut, remove overlays).
- `services/render-worker/tests/test_reframe.py`: 3 tests (aspect parsing, crop math, filter string).
- `services/render-worker/tests/test_stabilize.py`: 3 tests (filter strings, availability probe, clip stabilization mock).

## Verification

### Unit tests
```text
services/reason-worker/tests/ (excluding workflow): 169 passed
services/ingest-worker/tests/: 46 passed
services/render-worker/tests/: 25 passed
```

### Golden Render
```text
Suite: 25 passed, 0 failed, 0 skipped
```

### Full pytest
```text
4 failed, 710 passed, 30 skipped
```
The 4 failures are the same pre-existing issues from earlier waves:
- `tests/test_cutlist_gen.py::TestEffectsAndOverlays::test_highest_energy_slot_gets_vignette`
- `tests/test_cutlist_gen.py::TestShotAndBeatSnapping::test_slot_snaps_to_nearby_shot_boundary`
- `tests/test_cutlist_gen.py::TestSlotContiguityAndDurationCap::test_reference_shorter_than_song_caps_duration`
- `tests/test_integration_pipeline.py::TestEndToEndSmoke::test_full_pipeline_uses_multiple_clips_audio_and_no_bogus_overlays`

No new regressions.

## Known issues / follow-up
- `use_auto_reframe` defaults to a 9:16 crop. Future work: wire subject detection (SAM3 / object-edit pipeline) to pass a real `subject_box` into `reframe_filter`.
- `use_stabilization` currently adds `deshake` as a slot prefilter. Two-pass `vidstab` is implemented but not used by default because it requires a writable temp path and libvidstab support.
- `use_text_based_edits` currently supports cuts and overlay removal only. Extend to support `extend`, `trim`, and multi-command batch editing.
- Text edits happen after cutlist generation but before clip ranking; duration changes do not currently trigger a re-balance of slot density. Consider re-running slot generation if large regions are removed.

## Next step
Wave 7: Pro Edit Features (Part 2) — subject-aware keyframed reframe, beat-synced speed ramps v2, and AI object removal prep.
