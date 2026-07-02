"""Tests for CLAP-based song mood tagging."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared-py" / "src"))

import ingest_worker.song_mood as song_mood_module
from ingest_worker.song_mood import analyze_song, tag_song_section
from shared_py.models import BeatGrid, BeatSegment, SectionMoodTags, SongMoodProfile


def _fake_classifier(results):
    """Return a classifier callable that returns ``results`` sorted by score."""

    def classifier(audio, candidate_labels):
        # `audio` is ignored in the mock.
        return sorted(
            [{"label": label, "score": results.get(label, 0.0)} for label in candidate_labels],
            key=lambda x: x["score"],
            reverse=True,
        )

    return classifier


class TestTagSongSection:
    def test_returns_top_k_sorted(self, tmp_path, monkeypatch):
        wav_path = str(tmp_path / "segment.wav")
        # Create a tiny silent WAV via numpy + soundfile.
        import numpy as np
        import soundfile as sf

        sf.write(wav_path, np.zeros(4800, dtype=np.float32), 48000)

        fake = _fake_classifier({"aggressive": 0.9, "melancholic": 0.7, "uplifting": 0.1})
        monkeypatch.setattr(song_mood_module, "_load_clap_pipeline", lambda: fake)

        ranked = tag_song_section(wav_path, ["aggressive", "melancholic", "uplifting"], top_k=2)
        assert len(ranked) == 2
        assert ranked[0] == ("aggressive", pytest.approx(0.9))
        assert ranked[1] == ("melancholic", pytest.approx(0.7))

    def test_empty_candidates_returns_empty(self, tmp_path):
        wav_path = str(tmp_path / "segment.wav")
        import numpy as np
        import soundfile as sf

        sf.write(wav_path, np.zeros(4800, dtype=np.float32), 48000)
        assert tag_song_section(wav_path, [], top_k=3) == []


class TestAnalyzeSong:
    def test_caches_profile(self, tmp_path, monkeypatch):
        song_path = str(tmp_path / "song.wav")
        import numpy as np
        import soundfile as sf

        sf.write(song_path, np.zeros(48000 * 5, dtype=np.float32), 48000)

        fake = _fake_classifier(
            {tag: 1.0 if tag == "rock" else 0.1 for tag in song_mood_module.GENRE_TAGS}
        )
        # Mix in moods so every candidate label gets a deterministic score.
        original_fake = fake

        def classifier(audio, candidate_labels):
            if set(candidate_labels) == set(song_mood_module.MOOD_TAGS):
                return sorted(
                    [{"label": label, "score": 1.0 if label == "aggressive" else 0.05} for label in candidate_labels],
                    key=lambda x: x["score"],
                    reverse=True,
                )
            return original_fake(audio, candidate_labels)

        monkeypatch.setattr(song_mood_module, "_load_clap_pipeline", lambda: classifier)

        beat_grid = BeatGrid(
            bpm=120.0,
            beats=[0.0, 0.5, 1.0],
            downbeats=[0.0],
            beat_positions=[1, 2, 3],
            segments=[
                BeatSegment(start=0.0, end=2.5, label="intro"),
                BeatSegment(start=2.5, end=5.0, label="verse"),
            ],
        )

        cache_dir = tmp_path / "mood_cache"
        profile = analyze_song(song_path, beat_grid, cache_dir=cache_dir)

        assert isinstance(profile, SongMoodProfile)
        assert len(profile.section_moods) == 2
        assert profile.section_moods[0].section_label == "intro"
        assert profile.section_moods[1].section_label == "verse"
        assert len(profile.genre_tags) <= 3

        cache_file = cache_dir / song_mood_module._song_hash(song_path) / "mood_tags.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        assert "section_moods" in data
        assert len(data["section_moods"]) == 2

    def test_load_from_cache(self, tmp_path, monkeypatch):
        song_path = str(tmp_path / "song.wav")
        import numpy as np
        import soundfile as sf

        sf.write(song_path, np.zeros(48000 * 2, dtype=np.float32), 48000)
        beat_grid = BeatGrid(
            bpm=120.0,
            beats=[0.0, 0.5],
            downbeats=[0.0],
            beat_positions=[1, 2],
            segments=[BeatSegment(start=0.0, end=2.0, label="intro")],
        )
        cache_dir = tmp_path / "mood_cache"

        # Pre-populate cache.
        profile = SongMoodProfile(
            song_hash=song_mood_module._song_hash(song_path),
            genre_tags=[("rock", 0.99)],
            section_moods=[
                SectionMoodTags(
                    start_s=0.0,
                    end_s=2.0,
                    section_label="intro",
                    top_moods=[("aggressive", 0.9)],
                )
            ],
        )
        cache_file = cache_dir / profile.song_hash / "mood_tags.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(profile.model_dump_json(), encoding="utf-8")

        # If CLAP were called it would fail; cache prevents that.
        loaded = analyze_song(song_path, beat_grid, cache_dir=cache_dir)
        assert loaded.genre_tags == [("rock", 0.99)]
