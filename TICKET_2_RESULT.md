# TICKET 2 — SongMeaning-driven arc selection + persistence

## Verification
Re-rendered test-folder-2 with `--preview` after T1 fix.

### test-folder-2 (Kimi No Nawa / Sparkle)
```
narrativeMode: Tragic
storyBeats: {'GRIEF': 1, None: 5}
realPathRatio: 0.9090909090909091
```

The selected arc is `Tragic`, matching the bittersweet/loss sentiment of the song.
The single non-None story beat is `GRIEF`, a tragic-arc label. Preview mode only
emits 6 slots, so the distribution is sparse, but the arc is correct.

### batch2 regression check
```
narrativeMode: Trailer
realPathRatio: 0.9333333333333333
storyBeats: {'HOOK': 1, None: 7, 'WORLD': 1, 'VICTORY': 1}
```

Batch2 correctly selects `Trailer`, preserving its AMV/hype character.

## Code changes
1. `services/reason-worker/src/reason_worker/narrative_arcs.py`
   - Added `ROMANTIC_ARC` with beats: PEACE, LONGING, CRACK, LOSS, ACCEPTANCE.
   - Rewrote `select_arc()` to inspect `SongMeaning.narrative.sections[].lyric_sentiment`
     and `SongMeaning.section_moods`:
     - Tragic keywords → `TRAGIC_ARC`
     - Romantic moods → `ROMANTIC_ARC`
     - Triumphant moods + energy trough → `TRAILER_ARC`
     - Fallback → `CLASSICAL_ARC`
2. `services/shared-py/src/shared_py/models.py`: added `narrative_mode` to `CutList`.
3. `services/reason-worker/src/reason_worker/cutlist_gen.py`: passes `song_meaning` to
   `select_arc()` and writes `arc_template.name` to `cutlist.narrative_mode`.
4. `services/reason-worker/src/reason_worker/arc_anchor.py`: replaced hardcoded
   HOOK/WORLD/CONFLICT/CRISIS/VICTORY mapping with a generic semantic mapper that
   assigns any arc template's beats to narrative sections by emotional alignment.

## Result
PASS for Kimi No Nawa — arc is now `Tragic`, not the previous `None`/default-Trailer.
