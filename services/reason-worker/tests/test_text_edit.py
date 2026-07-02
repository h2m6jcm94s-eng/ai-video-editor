# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unit tests for text-based editing primitives."""

import pytest

from shared_py.models import CutList, CutListGlobals, Overlay, Slot
from reason_worker.text_edit import apply_text_edits, parse_edit_command


def _make_cutlist() -> CutList:
    slots = [
        Slot(index=0, start_s=0.0, duration_s=5.0, beat_index=0, section="verse", target_shot_type="medium", subject_hint="", motion_hint="static", energy_level=0.5),
        Slot(index=1, start_s=5.0, duration_s=5.0, beat_index=1, section="verse", target_shot_type="medium", subject_hint="", motion_hint="static", energy_level=0.5),
        Slot(index=2, start_s=10.0, duration_s=5.0, beat_index=2, section="chorus", target_shot_type="close_up", subject_hint="", motion_hint="static", energy_level=0.8),
    ]
    return CutList(globals=CutListGlobals(total_duration_s=15.0, tempo_bpm=120.0), slots=slots, overlays=[Overlay(text="hi", start_s=0.0, end_s=15.0)])


def test_parse_cut_command():
    op = parse_edit_command("cut from 0:05 to 0:10")
    assert op is not None
    assert op.action == "cut"
    assert op.start_s == 5.0
    assert op.end_s == 10.0


def test_apply_cut_removes_slot():
    cutlist = _make_cutlist()
    op = parse_edit_command("cut from 0:04 to 0:11")
    apply_text_edits(cutlist, [op])
    assert len(cutlist.slots) == 2
    assert cutlist.slots[0].start_s + cutlist.slots[0].duration_s <= 4.0
    assert cutlist.slots[1].start_s >= 11.0


def test_remove_overlays():
    cutlist = _make_cutlist()
    op = parse_edit_command("remove captions")
    apply_text_edits(cutlist, [op])
    assert cutlist.overlays == []
