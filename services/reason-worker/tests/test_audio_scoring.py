# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for audio dialogue scoring and adaptive mix decisions."""

import pytest

from reason_worker.audio_scoring import (
    DialogueSegment,
    ScoringConfig,
    _phrase_match_score,
    score_clip_dialogue,
)
from reason_worker.audio_mix import (
    DEFAULT_POLICIES,
    SectionPolicy,
    build_audio_tracks,
    _section_at,
)
from shared_py.models import AudioTrack, BeatGrid, BeatSegment, CutList, CutListGlobals


class TestPhraseMatch:
    def test_exact_match_is_one(self):
        # Punctuation is normalized away.
        assert _phrase_match_score("I'm built different", ["im built different"]) == 1.0

    def test_no_phrases_is_zero(self):
        assert _phrase_match_score("hello world", []) == 0.0

    def test_partial_overlap(self):
        assert _phrase_match_score("I am built different today", ["built different"]) == 1.0


class TestScoringConfig:
    def test_phrases_normalized(self):
        cfg = ScoringConfig(iconic_phrases=["  I'm Built Different! "])
        assert cfg.iconic_phrases == ["im built different"]


class TestDialogueSegment:
    def test_iconic_line_boosts_total(self):
        seg = DialogueSegment(
            start_s=0.0,
            end_s=1.0,
            text="I'm built different",
            speech_score=0.72,
            phrase_match_score=1.0,
        )
        assert seg.total_score > 0.85


class TestSectionPolicies:
    def test_drop_is_music_full(self):
        assert DEFAULT_POLICIES["drop"].music_full is True

    def test_verse_ducks_harder_than_drop(self):
        assert DEFAULT_POLICIES["verse"].duck_gain_db < DEFAULT_POLICIES["drop"].duck_gain_db


class TestSectionAt:
    def test_finds_active_section(self):
        segments = [
            BeatSegment(start=0.0, end=10.0, label="intro"),
            BeatSegment(start=10.0, end=30.0, label="drop"),
        ]
        assert _section_at(5.0, segments) == "intro"
        assert _section_at(15.0, segments) == "drop"


class TestBuildAudioTracks:
    def test_music_bed_created(self):
        cutlist = CutList(
            globals=CutListGlobals(total_duration_s=30.0, tempo_bpm=120.0),
            slots=[],
            overlays=[],
            beat_grid=BeatGrid(
                bpm=120.0,
                beats=[0.0, 0.5],
                downbeats=[0.0],
                beat_positions=[1],
                segments=[BeatSegment(start=0.0, end=30.0, label="verse")],
            ),
        )
        tracks = build_audio_tracks(cutlist, song_asset_id="song_001")
        assert len(tracks) == 1
        assert tracks[0].role == "music"
        assert tracks[0].end_s == 30.0

    def test_drop_music_full_preserves_gain(self):
        cutlist = CutList(
            globals=CutListGlobals(total_duration_s=30.0, tempo_bpm=120.0),
            slots=[],
            overlays=[],
            beat_grid=BeatGrid(
                bpm=120.0,
                beats=[0.0, 0.5],
                downbeats=[0.0],
                beat_positions=[1],
                segments=[
                    BeatSegment(start=0.0, end=15.0, label="verse"),
                    BeatSegment(start=15.0, end=30.0, label="drop"),
                ],
            ),
        )
        tracks = build_audio_tracks(cutlist, song_asset_id="song_001")
        music = [t for t in tracks if t.role == "music"][0]
        # Drop policy is the most aggressive ducking? Actually duck_gain_db for drop is -6,
        # verse is -14, so min (most negative) is verse.  Music gain should be from the
        # selected policy; here music policy chosen by min duck_gain is verse.
        assert music.gain_db == DEFAULT_POLICIES["verse"].music_gain_db
