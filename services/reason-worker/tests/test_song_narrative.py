# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Tests for Gemma-based song narrative labeling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reason_worker.song_narrative import analyze_song_narrative
from shared_py.llm_client import LLMClient
from shared_py.models import SectionMoodTags, SongMoodProfile, VocalEmotionCurve, VocalEmotionSample

# Import the ingest-side dataclass used by the module.
from ingest_worker.song_lyrics import LyricWord


class _MockLLMClient:
    """Returns canned responses for narrative section labeling."""

    def __init__(self, responses):
        self.responses = responses
        self.call_index = 0

    async def complete(self, **kwargs):
        response = self.responses[self.call_index % len(self.responses)]
        self.call_index += 1
        return response


@pytest.mark.asyncio
async def test_analyze_song_narrative_labels_sections(tmp_path: Path):
    mood_profile = SongMoodProfile(
        song_hash="abc",
        genre_tags=[("pop", 0.9)],
        section_moods=[
            SectionMoodTags(start_s=0.0, end_s=10.0, section_label="intro", top_moods=[("calm", 0.8)]),
            SectionMoodTags(start_s=10.0, end_s=30.0, section_label="verse", top_moods=[("melancholic", 0.7)]),
        ],
    )
    lyrics = [
        LyricWord(text="hello", start_s=0.0, end_s=1.0),
        LyricWord(text="world", start_s=1.5, end_s=2.5),
    ]
    vocal_curve = VocalEmotionCurve(
        song_hash="abc",
        samples=[
            VocalEmotionSample(t_center_s=2.0, dominant_emotion="calm", distribution={"calm": 0.8}, rms=0.1),
            VocalEmotionSample(t_center_s=15.0, dominant_emotion="sad", distribution={"sad": 0.7}, rms=0.2),
        ],
    )

    responses = [
        json.dumps({
            "lyric_sentiment": "quiet greeting",
            "story_role": "setup",
            "emotional_intensity": 0.25,
            "arc_beat_hint": "HOOK",
            "rationale": "intro sets the scene",
        }),
        json.dumps({
            "lyric_sentiment": "longing",
            "story_role": "reveal",
            "emotional_intensity": 0.65,
            "arc_beat_hint": "CONFLICT",
            "rationale": "verse introduces tension",
        }),
    ]

    narrative = await analyze_song_narrative(
        song_hash="abc",
        mood_profile=mood_profile,
        lyric_words=lyrics,
        vocal_curve=vocal_curve,
        llm_client=_MockLLMClient(responses),
        cache_dir=tmp_path,
    )

    assert len(narrative.sections) == 2
    assert narrative.sections[0].story_role == "setup"
    assert narrative.sections[0].arc_beat_hint == "HOOK"
    assert narrative.sections[1].story_role == "reveal"
    assert not narrative.skipped_sections


@pytest.mark.asyncio
async def test_analyze_song_narrative_skips_on_double_failure(tmp_path: Path):
    mood_profile = SongMoodProfile(
        song_hash="bad",
        genre_tags=[("pop", 0.9)],
        section_moods=[
            SectionMoodTags(start_s=0.0, end_s=10.0, section_label="intro", top_moods=[("calm", 0.8)]),
        ],
    )
    lyrics = [LyricWord(text="nope", start_s=0.0, end_s=1.0)]
    vocal_curve = VocalEmotionCurve(
        song_hash="bad",
        samples=[VocalEmotionSample(t_center_s=2.0, dominant_emotion="calm", distribution={"calm": 0.8}, rms=0.1)],
    )

    # Each section triggers two calls (initial + retry). Return garbage both times.
    responses = ["not json", "still not json"]

    narrative = await analyze_song_narrative(
        song_hash="bad",
        mood_profile=mood_profile,
        lyric_words=lyrics,
        vocal_curve=vocal_curve,
        llm_client=_MockLLMClient(responses),
        cache_dir=tmp_path,
    )

    assert len(narrative.sections) == 0
    assert len(narrative.skipped_sections) == 1
    assert narrative.skipped_sections[0]["reason"] == "gemma_json_failure"


@pytest.mark.asyncio
async def test_analyze_song_narrative_uses_cache(tmp_path: Path):
    cache_file = tmp_path / "abc" / "narrative.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({
            "song_hash": "abc",
            "sections": [{
                "start_s": 0.0,
                "end_s": 10.0,
                "section_label": "intro",
                "lyric_sentiment": "cached",
                "story_role": "setup",
                "emotional_intensity": 0.2,
                "arc_beat_hint": "HOOK",
                "rationale": "from cache",
            }],
            "skipped_sections": [],
        }),
        encoding="utf-8",
    )

    narrative = await analyze_song_narrative(
        song_hash="abc",
        mood_profile=SongMoodProfile(song_hash="abc", section_moods=[]),
        lyric_words=[],
        vocal_curve=VocalEmotionCurve(song_hash="abc"),
        llm_client=_MockLLMClient([]),
        cache_dir=tmp_path,
    )

    assert len(narrative.sections) == 1
    assert narrative.sections[0].lyric_sentiment == "cached"
