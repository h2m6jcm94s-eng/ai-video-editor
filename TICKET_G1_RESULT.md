# G1 — Spring/Overshoot Easing in Keyframe Engine

## Acceptance

```text
services\render-worker\tests\test_keyframes.py .................
services\render-worker\tests\test_layers.py .......
============================== 24 passed in 0.94s ==============================

Full suite: 886 passed, 31 skipped
```

## What was built

- `services/render-worker/src/render_worker/keyframes.py`
  - Added `spring` easing with a damped harmonic oscillator step response.
  - Tuned for ~5-8% overshoot and settling within 2% by `t=1.0`.
  - Implemented `ease_in`, `ease_out`, `ease_in_out` for `sample()` and FFmpeg expressions.
  - `normalize_track(..., default_easing)` overrides the model default for text/graphic layers.
- `services/render-worker/src/render_worker/layers.py`
  - Text layers default to `spring` easing on all keyframe tracks.
  - Added `text` layer type support (transparent canvas + `drawtext`).
- `services/shared-py/src/shared_py/models.py`
  - `Keyframe.easing` now includes `"spring"`.
  - `Layer.type` now includes `"text"`; added text styling fields.
- Tests
  - `services/render-worker/tests/test_keyframes.py`: spring overshoot/settle, FFmpeg expression, default-easing override.
  - `services/render-worker/tests/test_layers.py`: text layer defaults to spring.

## Notes

- The spring curve is normalized to the keyframe interval; for a 0→1 transition it overshoots above 1.0 then settles.
- Text/graphic layers get spring by default; explicit non-linear easings are preserved.
