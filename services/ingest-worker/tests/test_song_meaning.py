# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unit tests for SongMeaning aggregation."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ingest_worker import song_meaning
from shared_py.models import (
    BeatGrid,
    BeatSegment,
    MusicEventGrid,
    SectionMoodTags,
    SongMeaning,
    SongMoodProfile,
    VocalEmotionCurve,
    VocalEmotionSample,
)

SR = 22_050


def _make_song_wav(tmp_path: Path, duration_s: float = 1.0) -> str:
    path = tmp_path / "song.wav"
    t = np.linspace(0, duration_s, int(SR * duration_s))
    y = 0.1 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sf.write(path, y, SR)
    return str(path)


def test_song_hash_is_stable(tmp_path: Path):
    path = _make_song_wav(tmp_path)
    h1 = song_meaning._song_hash(path)
    h2 = song_meaning._song_hash(path)
    assert h1 == h2
    assert len(h1) == 32


def test_load_song_meaning_missing_returns_none(tmp_path: Path):
    path = _make_song_wav(tmp_path)
    assert song_meaning.load_song_meaning(path, cache_dir=tmp_path / "cache") is None


def test_song_meaning_model_round_trip(tmp_path: Path):
    meaning = SongMeaning(
        song_hash="abc",
        genre_tags=[("hip-hop", 0.95)],
        section_moods=[SectionMoodTags(start_s=0, end_s=10, section_label="verse", top_moods=[("dark", 0.8)])],
        vocal_emotion_curve=VocalEmotionCurve(
            song_hash="abc",
            samples=[VocalEmotionSample(t_center_s=1.0, dominant_emotion="happy", distribution={"happy": 0.9}, rms=0.1)],
        ),
        music_event_grid=MusicEventGrid(song_hash="abc", kick_times=[0.5, 1.5]),
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    cache_file = cache / "abc.json"
    cache_file.write_text(meaning.model_dump_json(), encoding="utf-8")

    loaded = SongMeaning(**json.loads(cache_file.read_text(encoding="utf-8")))
    assert loaded.song_hash == "abc"
    assert loaded.music_event_grid.kick_times == [0.5, 1.5]


def test_aggregate_song_meaning_combines_sub_analyses(tmp_path: Path, monkeypatch):
    path = _make_song_wav(tmp_path)
    beat_grid = BeatGrid(
        bpm=120.0,
        beats=[0.0, 0.5, 1.0],
        downbeats=[0.0],
        beat_positions=[1, 2, 3],
        segments=[BeatSegment(label="verse", start=0.0, end=1.0)],
    )

    mood_profile = SongMoodProfile(
        song_hash="mood-hash",
        genre_tags=[("hip-hop", 0.95)],
        section_moods=[SectionMoodTags(start_s=0, end_s=1, section_label="verse", top_moods=[("dark", 0.8)])],
    )
    vocal_curve = VocalEmotionCurve(
        song_hash="vocal-hash",
        samples=[VocalEmotionSample(t_center_s=0.5, dominant_emotion="happy", distribution={"happy": 0.9}, rms=0.1)],
    )
    event_grid = MusicEventGrid(song_hash="event-hash", kick_times=[0.25])

    # Monkey-patch expensive sub-analyses to return deterministic fixtures.
    monkeypatch.setattr(song_meaning, "detect_beats", lambda p: beat_grid)
    monkeypatch.setattr(song_meaning, "analyze_song", lambda p, bg, cache_dir: mood_profile)
    monkeypatch.setattr(
        song_meaning,
        "separate_song_stems",
        lambda p: {"drums": str(tmp_path / "drums.wav"), "vocals": str(tmp_path / "vocals.wav")},
    )
    monkeypatch.setattr(song_meaning, "transcribe_song_lyrics", lambda p: [])
    monkeypatch.setattr(song_meaning, "analyze_vocal_stem", lambda p, song_hash, cache_dir: vocal_curve)
    monkeypatch.setattr(song_meaning, "detect_music_events", lambda stems_dir, words, cache_dir: event_grid)

    cache_dir = tmp_path / "meaning"
    meaning = song_meaning.aggregate_song_meaning(path, beat_grid=beat_grid, cache_dir=cache_dir)

    assert meaning.genre_tags == [("hip-hop", 0.95)]
    assert len(meaning.section_moods) == 1
    assert len(meaning.vocal_emotion_curve.samples) == 1
    assert meaning.music_event_grid.kick_times == [0.25]
    assert (cache_dir / f"{meaning.song_hash}.json").exists()

    # Second call should load from cache and return the same object shape.
    meaning2 = song_meaning.aggregate_song_meaning(path, beat_grid=beat_grid, cache_dir=cache_dir)
    assert meaning2 == meaning
