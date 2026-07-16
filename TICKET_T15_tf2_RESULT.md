# T.15 — tf2 Golden Regression Gate

## Acceptance

```text
scripts/render_test_folder_2.py --feature-emotion-led-cuts --feature-wave-10
Render complete in 812.8s
Output: E:\work\ai_video_editor\test folder 2\output\output.mp4
real_path_ratio: 0.99  demo_grade: True
```

## Render metrics

| Metric | Value |
|---|---|
| Duration | 410.33 s |
| Resolution | 1920x1080 @ 30 fps |
| Bitrate | ~4.4 Mbps |
| Output size | 236 MB |
| Slots | 171 |
| Render path | real 99% / fallback 1% |
| Demo grade | True |

## Features exercised

- emotion-led cuts
- wave-10 effects pipeline
- speed ramps
- iconic quotes (dialogue path skipped due to no dialogue)
- audio ducking (fallback: no_dialogue_detected)
- kinetic text (fallback: no_high_energy_slots)

## Notes

- tf2 gate passes; T.16 is unblocked.
- Warnings observed are expected feasibility fallbacks (source window rewind, speed ramp clamp, segment extension); no render failures.
