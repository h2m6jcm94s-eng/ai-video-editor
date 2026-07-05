# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reason_worker.audio_scoring import DialogueSegment, WordTimestamp
from reason_worker.captions import (
    _group_words_into_phrases,
    generate_caption_overlays_from_segments,
    CaptionWord,
)


def _cw(text, start, end, slot_index=0, slot_start=0.0):
    return CaptionWord(
        text=text,
        start_s=start,
        end_s=end,
        slot_index=slot_index,
        slot_start_s=slot_start,
    )


def test_group_words_preserves_subwords():
    words = [
        _cw("hello", 0.0, 0.2),
        _cw("world", 0.25, 0.5),
        _cw("again", 1.0, 1.2),
    ]
    phrases = _group_words_into_phrases(words, max_words=2, max_gap_s=0.35)
    assert len(phrases) == 2
    assert phrases[0].text == "hello world"
    assert len(phrases[0].words) == 2
    assert phrases[0].words[0].text == "hello"
    assert phrases[0].words[1].text == "world"
    assert phrases[1].text == "again"
    assert len(phrases[1].words) == 1


def test_group_words_splits_on_large_gap():
    words = [
        _cw("one", 0.0, 0.2),
        _cw("two", 0.7, 0.9),
    ]
    phrases = _group_words_into_phrases(words, max_words=4, max_gap_s=0.35)
    assert len(phrases) == 2


def test_generate_caption_overlays_word_by_word():
    segments = [
        DialogueSegment(
            start_s=0.0,
            end_s=1.0,
            text="hello world",
            words=[
                WordTimestamp("hello", 0.0, 0.4),
                WordTimestamp("world", 0.5, 0.9),
            ],
        )
    ]
    slot_segments = [(0, "clip_0", 0.0, 10.0, segments)]
    overlays = generate_caption_overlays_from_segments(
        slot_segments,
        mood="joyful",
        energy=0.6,
    )
    assert len(overlays) == 1
    ov = overlays[0]
    assert ov.text == "HELLO WORLD"
    assert ov.animation == "word_by_word"
    assert ov.highlight_color == "#FFE600"
    assert ov.words is not None
    assert len(ov.words) == 2
    assert ov.words[0].text == "hello"
    assert ov.words[0].start_s == 10.0
    assert ov.words[1].end_s == 10.9


def test_generate_caption_overlays_mood_aware_font():
    segments = [
        DialogueSegment(
            start_s=0.0,
            end_s=0.5,
            text="hey",
            words=[WordTimestamp("hey", 0.0, 0.5)],
        )
    ]
    overlays = generate_caption_overlays_from_segments(
        [(0, "clip_0", 0.0, 0.0, segments)],
        mood="aggressive",
        energy=0.9,
    )
    assert overlays[0].font == "Anton"

    overlays = generate_caption_overlays_from_segments(
        [(0, "clip_0", 0.0, 0.0, segments)],
        mood="melancholic",
        energy=0.2,
    )
    assert overlays[0].font == "Cinzel"


def test_generate_caption_overlays_empty_segments():
    assert generate_caption_overlays_from_segments([]) == []


def test_high_energy_phrase_uses_karaoke_reveal():
    segments = [
        DialogueSegment(
            start_s=0.0,
            end_s=1.0,
            text="hello world",
            words=[
                WordTimestamp("hello", 0.0, 0.4),
                WordTimestamp("world", 0.5, 0.9),
            ],
        )
    ]
    overlays = generate_caption_overlays_from_segments(
        [(0, "clip_0", 0.0, 10.0, segments)],
        slot_energy={0: 0.9},
    )
    assert len(overlays) == 1
    assert overlays[0].animation == "karaoke_reveal"
