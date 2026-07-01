# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

from shared_py.feature_quality_checks import (
    check_heatmap,
    check_aesthetic,
    check_iconic_quotes,
    check_identity_matte,
    check_dialogue,
    check_save_the_cat,
    check_auto_lut,
    check_style_genome,
    check_demucs,
    check_momentum,
)
from shared_py.models import CutList, CutListGlobals, Slot, StyleGenome


class MockWindow:
    def __init__(self, score):
        self.score = score


class TestCheckHeatmap:
    def test_passes_with_good_coverage_and_variance(self):
        windows = [MockWindow(0.1 * i) for i in range(1, 21)]
        ok, reason = check_heatmap(windows)
        assert ok is True
        assert reason == ""

    def test_fails_when_empty(self):
        ok, reason = check_heatmap([])
        assert ok is False
        assert "no windows" in reason

    def test_fails_low_coverage(self):
        windows = [MockWindow(0.0)] * 10 + [MockWindow(0.5)]
        ok, reason = check_heatmap(windows)
        assert ok is False
        assert "coverage" in reason

    def test_fails_low_variance(self):
        windows = [MockWindow(0.5)] * 20
        ok, reason = check_heatmap(windows)
        assert ok is False
        assert "std" in reason


class TestCheckAesthetic:
    def test_passes_sane_scores(self):
        ok, reason = check_aesthetic([0.4, 0.5, 0.6, 0.55])
        assert ok is True

    def test_fails_empty(self):
        ok, reason = check_aesthetic([])
        assert ok is False

    def test_fails_low_mean(self):
        ok, reason = check_aesthetic([0.01, 0.02])
        assert ok is False
        assert "mean" in reason


class TestCheckIconicQuotes:
    def test_passes_with_quotes(self):
        ok, reason = check_iconic_quotes([{"importance": 0.7}])
        assert ok is True

    def test_fails_empty(self):
        ok, reason = check_iconic_quotes([])
        assert ok is False


class TestCheckIdentityMatte:
    def test_passes_with_detections(self):
        ok, reason = check_identity_matte([{"clip_id": "c1"}])
        assert ok is True

    def test_fails_empty_dict(self):
        ok, reason = check_identity_matte({})
        assert ok is False

    def test_passes_mask_paths(self):
        ok, reason = check_identity_matte({"c1": "/tmp/mask.mp4"})
        assert ok is True


class TestCheckDialogue:
    def test_passes_with_dialogue_track(self):
        tracks = [{"role": "music"}, {"role": "dialogue"}]
        ok, reason = check_dialogue(tracks)
        assert ok is True

    def test_fails_without_dialogue(self):
        tracks = [{"role": "music"}]
        ok, reason = check_dialogue(tracks)
        assert ok is False
        assert "dialogue-role" in reason


class TestCheckSaveTheCat:
    def test_passes_when_slots_have_beats(self):
        cutlist = CutList(
            globals=CutListGlobals(total_duration_s=10.0, tempo_bpm=120.0),
            slots=[
                Slot(
                    index=0,
                    start_s=0.0,
                    duration_s=1.0,
                    beat_index=0,
                    section="verse",
                    target_shot_type="medium",
                    subject_hint="",
                    motion_hint="static",
                    energy_level=0.5,
                    story_beat="opening_image",
                )
            ],
        )
        ok, reason = check_save_the_cat(cutlist)
        assert ok is True

    def test_fails_when_no_story_beats(self):
        cutlist = CutList(
            globals=CutListGlobals(total_duration_s=10.0, tempo_bpm=120.0),
            slots=[
                Slot(
                    index=0,
                    start_s=0.0,
                    duration_s=1.0,
                    beat_index=0,
                    section="verse",
                    target_shot_type="medium",
                    subject_hint="",
                    motion_hint="static",
                    energy_level=0.5,
                )
            ],
        )
        ok, reason = check_save_the_cat(cutlist)
        assert ok is False
        assert "story beat" in reason


class TestCheckAutoLut:
    def test_passes_when_lut_extracted(self):
        ok, reason = check_auto_lut(
            {"reference_present": True, "lut_extracted": True, "lut_storage_key": "lut.cube"}
        )
        assert ok is True

    def test_passes_when_no_reference(self):
        ok, reason = check_auto_lut({"reference_present": False})
        assert ok is True

    def test_fails_when_reference_but_no_lut(self):
        ok, reason = check_auto_lut({"reference_present": True, "lut_extracted": False})
        assert ok is False


class TestCheckStyleGenome:
    def test_passes_with_genome(self):
        ok, reason = check_style_genome(StyleGenome())
        assert ok is True

    def test_fails_empty_families(self):
        ok, reason = check_style_genome({"families": {}})
        assert ok is False


class TestCheckDemucs:
    def test_passes_with_stems(self):
        ok, reason = check_demucs({"vocals": "vocals.wav"})
        assert ok is True

    def test_fails_empty(self):
        ok, reason = check_demucs([])
        assert ok is False


class TestCheckMomentum:
    def test_passes_with_variance(self):
        ok, reason = check_momentum([0.5, 0.7, 0.2, 0.9])
        assert ok is True

    def test_fails_low_variance(self):
        ok, reason = check_momentum([0.5, 0.5, 0.5])
        assert ok is False
        assert "std" in reason
