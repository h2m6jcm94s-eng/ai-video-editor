# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Text-based editing primitives for adjusting a generated cutlist."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from shared_py.models import CutList, Slot


@dataclass
class EditOperation:
    action: str  # "cut", "trim", "extend", "remove_overlays"
    start_s: float
    end_s: float
    payload: Optional[dict] = None


def _parse_timestamp(text: str) -> float:
    """Parse 'mm:ss', 'm:ss', or raw seconds into seconds."""
    text = text.strip()
    if ":" in text:
        parts = text.split(":")
        if len(parts) == 2:
            m, s = parts
            return float(m) * 60 + float(s)
        if len(parts) == 3:
            h, m, s = parts
            return float(h) * 3600 + float(m) * 60 + float(s)
    return float(text)


def parse_edit_command(command: str) -> Optional[EditOperation]:
    """Parse a single natural-language edit command into an operation."""
    command = command.lower().strip()
    if not command:
        return None

    # "cut from 0:05 to 0:10" / "remove 0:05-0:10"
    range_match = re.search(r"(?:from\s+)?(\d+:\d+(?::\d+)?|\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+:\d+(?::\d+)?|\d+(?:\.\d+)?)", command)
    if range_match:
        start_s = _parse_timestamp(range_match.group(1))
        end_s = _parse_timestamp(range_match.group(2))
        if "cut" in command or "remove" in command or "delete" in command:
            return EditOperation("cut", start_s, end_s)
        if "trim" in command:
            return EditOperation("trim", start_s, end_s)
        if "extend" in command:
            return EditOperation("extend", start_s, end_s)

    if "remove overlay" in command or "remove text" in command or "remove captions" in command:
        return EditOperation("remove_overlays", 0.0, 0.0)

    return None


def apply_text_edits(cutlist: CutList, operations: List[EditOperation]) -> CutList:
    """Apply a list of edit operations to a cutlist in-place and return it."""
    for op in operations:
        if op.action == "cut":
            _cut_region(cutlist, op.start_s, op.end_s)
        elif op.action == "trim":
            _cut_region(cutlist, op.start_s, op.end_s)
        elif op.action == "remove_overlays":
            cutlist.overlays = []
    return cutlist


def _cut_region(cutlist: CutList, start_s: float, end_s: float) -> None:
    """Remove or shorten slots that fall inside the cut region."""
    if start_s >= end_s:
        return
    new_slots: List[Slot] = []
    for slot in cutlist.slots:
        slot_start = slot.start_s
        slot_end = slot.start_s + slot.duration_s
        if slot_end <= start_s or slot_start >= end_s:
            new_slots.append(slot)
            continue
        if slot_start < start_s and slot_end > end_s:
            # Slot spans the cut; shorten it to the part before the cut.
            slot.duration_s = round(max(0.0, start_s - slot_start), 3)
            new_slots.append(slot)
        elif slot_start < start_s:
            slot.duration_s = round(max(0.0, start_s - slot_start), 3)
            new_slots.append(slot)
        elif slot_end > end_s:
            slot.start_s = round(end_s, 3)
            slot.duration_s = round(max(0.0, slot_end - end_s), 3)
            new_slots.append(slot)
        # else slot fully inside cut -> dropped.
    cutlist.slots = [s for s in new_slots if s.duration_s > 0.05]
    _reindex_slots(cutlist)


def _reindex_slots(cutlist: CutList) -> None:
    for i, slot in enumerate(sorted(cutlist.slots, key=lambda s: s.start_s)):
        slot.index = i
