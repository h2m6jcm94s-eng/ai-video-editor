# G2 — Blend Modes + Mattes in Layer Compositor

## Acceptance

```text
services\render-worker\tests\test_layers.py .................
============================== 15 passed in 1.05s ==============================

Full suite: 894 passed, 31 skipped
```

## What was built

- `services/render-worker/src/render_worker/layers.py`
  - Added `blend_mode` support via FFmpeg `blend` filter for `screen`, `multiply`, `overlay`, `addition`, `lighten`, `darken`.
  - Added `matte_source` alpha-matte support via `alphamerge`.
  - Refactored filter graph generation so each layer is first prepared (color/text/image/video), optionally matted, then positioned/blended.
  - Fixed alpha handling: `geq=lum='255':a='...'` now valid for FFmpeg 7+.
- `services/shared-py/src/shared_py/models.py`
  - Added `matte_source` field to `Layer`.
- Tests
  - Parametrized blend-mode filter check.
  - Matte source adds extra input + `alphamerge`.
  - Real 3-layer demo render (base + normal + screen + multiply) and frame extraction.

## Notes

- `normal` blend mode continues to use `overlay`.
- Matte sources are expected as grayscale images/videos and are scaled to the canvas.
