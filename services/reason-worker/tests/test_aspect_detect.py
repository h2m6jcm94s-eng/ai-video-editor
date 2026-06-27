# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for aspect-ratio preset detection."""

from reason_worker.aspect_detect import detect_aspect_preset


def test_detect_aspect_16_9():
    assert detect_aspect_preset(1920, 1080) == "youtube_16_9"


def test_detect_aspect_9_16():
    assert detect_aspect_preset(1080, 1920) == "reels_9_16"


def test_detect_aspect_square():
    assert detect_aspect_preset(1080, 1080) == "square_1_1"


def test_detect_aspect_cinema():
    assert detect_aspect_preset(2048, 858) == "cinema_2_35"


def test_detect_aspect_falls_back():
    assert detect_aspect_preset(800, 600) == "youtube_16_9"


def test_detect_aspect_missing_dims():
    assert detect_aspect_preset(None, 1080) == "youtube_16_9"
    assert detect_aspect_preset(1920, 0) == "youtube_16_9"
