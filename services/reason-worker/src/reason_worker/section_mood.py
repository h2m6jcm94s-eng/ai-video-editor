# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Helpers to resolve the dominant section mood for a slot."""

from __future__ import annotations

from typing import Dict, List, Optional

from shared_py.models import Slot, SongMeaning


def section_mood_for_slot(slot: Slot, song_meaning: Optional[SongMeaning]) -> Optional[str]:
    """Return the top CLAP mood for the song section overlapping the slot."""
    if not song_meaning or not song_meaning.section_moods:
        return None
    slot_start = slot.start_s
    for section in song_meaning.section_moods:
        if section.start_s <= slot_start < section.end_s and section.top_moods:
            return section.top_moods[0][0]
    return None


def build_section_moods(
    slots: List[Slot],
    song_meaning: Optional[SongMeaning],
) -> Dict[int, str]:
    """Map slot index → dominant section mood."""
    return {slot.index: mood for slot in slots if (mood := section_mood_for_slot(slot, song_meaning))}
