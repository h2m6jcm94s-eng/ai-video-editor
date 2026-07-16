# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Unit tests for the dedicated effect filter primitives."""

from render_worker.edits.zoom_punch import zoom_punch_filter
from render_worker.edits.focus_pull import focus_pull_filter
from render_worker.edits.vignette import vignette_filter
from render_worker.edits.chromatic_aberration import chromatic_aberration_filter
from render_worker.edits.hm_mvgd_hm import hm_mvgd_hm_filter


def test_zoom_punch_filter_uses_crop_and_ramp():
    f = zoom_punch_filter(0.0, 1.0, target_scale=1.5, duration_ms=300, fps=30)
    assert "crop=" in f
    assert "1.5" in f
    assert "(iw-ow)*0.5" in f


def test_focus_pull_filter_returns_two_blur_passes():
    filters = focus_pull_filter(0.0, 1.0, target_blur=4.0, duration_ms=600, fps=30)
    assert len(filters) == 2
    assert all("gblur" in f for f in filters)
    assert "sigma=1.60" in filters[0]
    assert "sigma=4.00" in filters[1]


def test_vignette_filter_contains_intensity():
    f = vignette_filter(0.0, 2.0, intensity=0.4)
    assert "vignette=" in f
    assert "PI/0.6" in f
    assert "between(t\\,0.000\\,2.000)" in f


def test_chromatic_aberration_filter_uses_rgbashift():
    f = chromatic_aberration_filter(0.5, 1.5, shift_x=4, shift_y=1, intensity=0.5)
    assert "rgbashift=" in f
    assert "rh=" in f
    assert "bv=" in f
    assert "between(t\\,0.500\\,1.500)" in f


def test_hm_mvgd_hm_filter_chains_eq_and_colorbalance():
    f = hm_mvgd_hm_filter(0.0, 1.0, strength=0.5, warmth=0.1, tint=0.0)
    assert "eq=" in f
    assert "colorbalance=" in f
    assert "between(t\\,0.000\\,1.000)" in f
