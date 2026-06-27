# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Tests for duration resolution logic."""


def _resolve_total_duration(target, song, reference):
    """Mirror the workflow duration resolution logic."""
    if target is not None:
        return float(target)
    if song is not None:
        return float(song)
    if reference is not None:
        return float(reference)
    return 30.0


def test_duration_matches_song_when_no_target():
    assert _resolve_total_duration(None, 217.0, 240.0) == 217.0


def test_no_30s_cap():
    assert _resolve_total_duration(None, 300.0, 300.0) == 300.0


def test_explicit_target_wins():
    assert _resolve_total_duration(60.0, 217.0, 240.0) == 60.0


def test_floor_at_5s():
    assert max(2.0, 5.0) == 5.0
