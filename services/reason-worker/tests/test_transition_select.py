# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import pytest

from reason_worker.transition_select import select_xfade


def test_whip_left_uses_hlslice():
    assert select_xfade("left", "left", "whip") == "hlslice"


def test_whip_right_uses_hrslice():
    assert select_xfade("right", "right", "whip") == "hrslice"


def test_hard_cut_with_motion_uses_hard_cut():
    assert select_xfade("left", "right", "hard_cut") == "hard_cut"


def test_hard_cut_still_uses_fade():
    assert select_xfade("still", "still", "hard_cut") == "fade"


def test_match_cut_same_motion_uses_dissolve():
    assert select_xfade("left", "left", "match_cut") == "dissolve"


def test_dissolve_archetype_uses_dissolve():
    assert select_xfade("left", "right", "dissolve") == "dissolve"


def test_fade_archetype_uses_fade():
    assert select_xfade("still", "still", "fade") == "fade"
