# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import CutList, CutListGlobals, Slot, BehaviorVector
from reason_worker.audio_mix import _dialogue_segments_for_slot
from reason_worker.audio_scoring import DialogueSegment, ScoringConfig


def _make_slot(source_window_start_s=None, duration_s=5.0, selected_clip_id="c1"):
    return Slot(
        index=0,
        start_s=120.0,
        duration_s=duration_s,
        beat_index=0,
        section="verse",
        target_shot_type="medium",
        subject_hint="person",
        motion_hint="static",
        energy_level=0.5,
        selected_clip_id=selected_clip_id,
        source_window_start_s=source_window_start_s,
    )


def test_dialogue_window_defaults_to_clip_start_when_no_source_window():
    """Regression for PR #9: missing clip audio when source_window_start_s is None.

    The window must be clip-relative (default 0.0), not timeline-relative, so a
    dialogue segment at the beginning of the clip is not discarded.
    """
    slot = _make_slot(source_window_start_s=None)
    cfg = ScoringConfig(min_dialogue_score=0.5)

    def fake_score(_path, cfg=None):
        return [
            DialogueSegment(start_s=0.2, end_s=1.5, speech_score=0.8, phrase_match_score=0.0),
            DialogueSegment(start_s=10.0, end_s=11.0, speech_score=0.8, phrase_match_score=0.0),
        ]

    original = _dialogue_segments_for_slot.__globals__["score_clip_dialogue"]
    try:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = fake_score
        segs = _dialogue_segments_for_slot(slot, "dummy.mp4", cfg, BehaviorVector())
    finally:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = original

    assert len(segs) == 1
    assert segs[0].start_s == 0.2
    assert segs[0].end_s == 1.5


def test_dialogue_window_respects_source_window_start():
    """Only dialogue inside the chosen source window should be kept."""
    slot = _make_slot(source_window_start_s=5.0, duration_s=4.0)
    cfg = ScoringConfig(min_dialogue_score=0.5)

    def fake_score(_path, cfg=None):
        return [
            DialogueSegment(start_s=0.5, end_s=1.5, speech_score=0.8, phrase_match_score=0.0),
            DialogueSegment(start_s=6.0, end_s=7.5, speech_score=0.8, phrase_match_score=0.0),
        ]

    original = _dialogue_segments_for_slot.__globals__["score_clip_dialogue"]
    try:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = fake_score
        segs = _dialogue_segments_for_slot(slot, "dummy.mp4", cfg, BehaviorVector())
    finally:
        _dialogue_segments_for_slot.__globals__["score_clip_dialogue"] = original

    assert len(segs) == 1
    assert segs[0].start_s == 1.0  # 6.0 - 5.0
    assert segs[0].end_s == 2.5  # 7.5 - 5.0, clamped to duration 4.0 -> min(4,2.5)=2.5


import numpy as np
import soundfile as sf

from shared_py.models import AudioTrack, MusicEventGrid, SongMeaning, VocalEmotionCurve, VocalEmotionSample
from reason_worker.audio_mix import _apply_jl_cuts, _apply_stem_aware_ducking


def _make_wav(path: Path, duration_s: float = 5.0):
    sr = 22050
    t = np.linspace(0, duration_s, int(sr * duration_s))
    y = 0.1 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sf.write(path, y, sr)
    return str(path)


def test_apply_jl_cuts_extends_dialogue_track(tmp_path: Path):
    slots = [
        Slot(index=0, start_s=10.0, duration_s=2.0, beat_index=0, section="verse", target_shot_type="medium", subject_hint="", motion_hint="static", energy_level=0.5),
        Slot(index=1, start_s=12.0, duration_s=2.0, beat_index=1, section="verse", target_shot_type="medium", subject_hint="", motion_hint="static", energy_level=0.5),
    ]
    clip_path = _make_wav(tmp_path / "clip.wav", duration_s=10.0)
    track = AudioTrack(
        asset_id="c1",
        role="dialogue",
        start_s=12.0,
        end_s=13.0,
        source_start_s=2.0,
        source_end_s=3.0,
        slot_index=1,
    )

    _apply_jl_cuts([track], slots, {"c1": clip_path}, total_duration=20.0)

    assert track.j_cut_lead_in_s == 0.0  # slot 1 starts right after slot 0, no lead-in room
    assert track.l_cut_tail_s > 0.0
    assert track.end_s > 13.0


def test_apply_stem_aware_ducking_disables_duck_on_bass_drop():
    tracks = [
        AudioTrack(asset_id="song", role="music", start_s=0.0, end_s=10.0),
    ]
    meaning = SongMeaning(
        song_hash="x",
        music_event_grid=MusicEventGrid(song_hash="x", bass_drop_times=[5.0]),
    )

    _apply_stem_aware_ducking(tracks, meaning, total_duration=10.0)

    assert tracks[0].duck_disabled is True


def test_apply_stem_aware_ducking_aggressive_on_high_arousal():
    tracks = [
        AudioTrack(asset_id="song", role="music", start_s=0.0, end_s=10.0, duck_gain_db=-10.0),
    ]
    meaning = SongMeaning(
        song_hash="x",
        vocal_emotion_curve=VocalEmotionCurve(
            song_hash="x",
            samples=[
                VocalEmotionSample(t_center_s=5.0, dominant_emotion="happy", distribution={"happy": 0.9}, rms=0.1),
            ],
        ),
    )

    _apply_stem_aware_ducking(tracks, meaning, total_duration=10.0)

    assert tracks[0].duck_gain_db < -10.0
