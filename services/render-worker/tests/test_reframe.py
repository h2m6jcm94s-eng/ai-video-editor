# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unit tests for auto-reframe helpers."""

import pytest

from render_worker.reframe import compute_reframe_crop, parse_aspect_ratio


def test_parse_aspect_ratio():
    assert parse_aspect_ratio("9:16") == pytest.approx(0.5625, abs=0.001)
    assert parse_aspect_ratio("16:9") == pytest.approx(1.777, abs=0.001)
    assert parse_aspect_ratio("1:1") == pytest.approx(1.0, abs=0.001)


def test_compute_reframe_crop_wide_to_tall():
    # 16:9 -> 9:16 should crop horizontally.
    x, y, w, h = compute_reframe_crop(1920, 1080, "9:16")
    assert h == 1080
    assert w < 1920
    assert x > 0 or x == (1920 - w) // 2
    assert w / h == pytest.approx(9 / 16, abs=0.05)


def test_compute_reframe_crop_centered_on_subject():
    x, y, w, h = compute_reframe_crop(1920, 1080, "9:16", subject_box=(0.8, 0.5, 0.1, 0.2))
    # Crop should be shifted toward the right side where subject is.
    assert x > (1920 - w) // 2 - 50
