# T.15 Extended Gate Result (G1/G2/G5 completed; G3/G4 blocked)

## Summary

- G1 spring easing + text layer support — ✅ committed.
- G2 blend modes + alpha mattes — ✅ committed.
- G5 Python verb registry + generated TS export — ✅ committed.
- G3 SAM3 masklets / camera-motion envelope — ❌ blocked by missing SAM3 runtime / HF token.
- G4 real world text behind subject — ❌ blocked by missing SAM3 runtime / HF token.
- See `ROOT_CAUSE_G3G4.md` for the dependency failure.

## Golden regression — batch2 (all flags)

```text
tests/golden_render/run.py --feature-emotion-led-cuts --feature-wave-8 --feature-wave-9 --feature-wave-10
Suite: 40 passed, 0 failed, 0 skipped
Expected checks: 36 checked, 0 required failures, 0 optional failures
```

Key metrics:

- real_path_ratio=1.0
- slot_window_fallback_count=0
- audio_ducking_real, kinetic_text_real, captions_real, speed_ramps_real all real
- transition_variety=7 distinct archetypes
- match_cuts_present=1
- zoom_punch_ins_on_kicks=43/79

## Golden regression — tf2

```text
scripts/render_test_folder_2.py --feature-emotion-led-cuts --feature-wave-10
Render complete in 812.8s
Output: E:\work\ai_video_editor\test folder 2\output\output.mp4
real_path_ratio: 0.99  demo_grade: True
```

- Duration: 410.33 s
- Resolution: 1920x1080 @ 30 fps
- Slots: 171

## Full Python test suite

```text
pytest tests/ services/
899 passed, 31 skipped, 20 warnings
```

## TypeScript checks

```text
pnpm typecheck
4 successful (shared-types, web, api)
```

## API parser tests

```text
pnpm --filter @ai-video-editor/api test -- src/test/commands.test.ts
5 passed
```

## Notes

- G1/G2/G5 are on `origin/main`.
- G3/G4 cannot proceed without a provisioned SAM3 runtime and Hugging Face access.
- The pre-existing `ai.test.ts` CUTLIST_SCHEMA_DRIFT failures (2 tests) are unchanged and unrelated to this work.
