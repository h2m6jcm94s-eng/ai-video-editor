# T.15 S3–S4 — Depth Verbs + World Text

## Acceptance

```text
services\render-worker\tests\test_camera_motion.py ....
============================== 4 passed in 0.21s ===============================
```

## What was built

### S3 Depth verbs
- Extended `services/render-worker/src/render_worker/edits/camera_motion.py` with:
  - `depth_push`
  - `depth_parallax_left`
  - `depth_parallax_right`
- Added `DepthVerbParams` to `services/shared-py/src/shared_py/models.py`
- Added effect types `depth_push`, `depth_parallax_left`, `depth_parallax_right` to `Effect`
- Wired compiler dispatch in `services/render-worker/src/render_worker/compiler.py`
- Registered depth verbs in the Operation Ledger with `prerequisites=["depth"]`
- Added depth-verb schemas to `packages/shared-types/src/effects.ts`

### S4 World text
- Added `WorldTextParams` to `services/shared-py/src/shared_py/models.py`
- Added effect type `world_text` to `Effect`
- Wired compiler dispatch: renders text through existing `_drawtext_filter` with font size scaled by `depth` cue
- Logs `world_text_depth_cue` with depth value
- Registered `world_text` in the Operation Ledger with `prerequisites=["depth"]`
- Added `world_text` schema to `packages/shared-types/src/effects.ts`

## Notes

- World text currently renders as a scaled text overlay; true world-space occlusion/perspective projection is planned for T20.7 text expansion.
- Depth verbs use the same `zoompan` filter path as the F3 camera channel, with presets chosen to suggest spatial depth.
