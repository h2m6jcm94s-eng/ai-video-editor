# TICKET 1 — Fix `no_path_declared` FeatureTracer decoration

## Verification
Re-rendered test-folder-2 with `--preview` after deleting the clip-emotion cache.

### Targeted unit check
```
profile primary: intrigue
profile confidence: 0.2438494165427983
FeaturePathReport(feature='clip_emotion', gated_in=True, real_path_ran=True, ...)
OK: clip_emotion real path traced successfully
```

### Preview render cutlist (test folder 2)
```
narrativeMode: Tragic
realPathRatio: 0.9090909090909091
fallbacks: {('audio_ducking', 'gate:no_dialogue_detected'): 1}
```

### Check: no `no_path_declared` entries
The only fallback in the feature runtime report is `audio_ducking::gate:no_dialogue_detected`, which is a real gate decision.
There are **zero** `no_path_declared` entries.

## Code change
- `services/ingest-worker/src/ingest_worker/clip_emotion.py`: added `ft.real()` after `ft.signature(...)` on the happy path of `compute_clip_emotion_profile`.

## Result
PASS — `clip_emotion` now traces its real path, and the downstream ranker/composer receives actual emotion profiles instead of silently-fallback `None` signals.
