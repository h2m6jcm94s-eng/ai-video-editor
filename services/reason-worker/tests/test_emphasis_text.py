# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import WordTiming
from reason_worker.emphasis_text import pick_emphasis_words, mark_emphasis_in_words


def test_repeated_words_are_emphasised():
    words = [
        WordTiming(text="rise", start_s=0.0, end_s=0.2),
        WordTiming(text="again", start_s=0.3, end_s=0.5),
        WordTiming(text="we", start_s=0.6, end_s=0.7),
        WordTiming(text="rise", start_s=0.8, end_s=1.0),
    ]
    chosen = pick_emphasis_words(words, energy=0.9)
    assert "rise" in chosen


def test_stopwords_are_not_emphasised():
    words = [
        WordTiming(text="the", start_s=0.0, end_s=0.1),
        WordTiming(text="and", start_s=0.2, end_s=0.3),
        WordTiming(text="but", start_s=0.4, end_s=0.5),
    ]
    chosen = pick_emphasis_words(words, energy=0.9)
    assert not chosen


def test_mark_emphasis_sets_flag():
    words = [
        WordTiming(text="rise", start_s=0.0, end_s=0.2),
        WordTiming(text="again", start_s=0.3, end_s=0.5),
        WordTiming(text="rise", start_s=0.8, end_s=1.0),
    ]
    marked = mark_emphasis_in_words(words, energy=0.9)
    assert any(w.text == "rise" and w.is_emphasis for w in marked)
