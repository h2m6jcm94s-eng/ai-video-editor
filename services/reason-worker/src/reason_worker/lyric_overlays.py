# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Kinetic text / lyric overlay generation for cut-list slots."""

from typing import Any, Dict, Optional

from shared_py.models import Slot


def generate_slot_text_overlay(
    slot: Slot,
    beat_grid: Optional[Any] = None,
    song_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return kinetic text for a slot.

    v0 does not perform real lyric extraction, so this returns ``None`` unless
    a caller provides song lyrics through ``song_metadata``. Hard-coded section
    labels (``BUILT DIFFERENT``, ``DROP``, etc.) have been removed because they
    are not the actual lyrics and produce meaningless overlays.
    """
    # TODO: wire Whisper word-level lyrics and pick the word whose onset falls
    # inside the slot's timeline window.
    if song_metadata is None:
        return None
    lyrics = song_metadata.get("lyrics", [])
    if not lyrics:
        return None
    # Placeholder for lyric-aware selection: choose a word in the slot window.
    for word in lyrics:
        onset = getattr(word, "onset_s", word.get("onset_s"))
        if onset is None:
            continue
        if slot.start_s <= onset <= slot.start_s + slot.duration_s:
            text = getattr(word, "text", word.get("text"))
            if text:
                return str(text).upper()
    return None


def should_render_behind_subject(slot: Slot) -> bool:
    """Return True when the slot's text should be composited behind the subject.

    Requires kinetic text to be enabled, the z-layer to be ``behind_subject``,
    and identity-aware protagonist matting metadata to be present.
    """
    if not slot.enable_kinetic_text:
        return False
    if slot.text_z_layer != "behind_subject":
        return False
    if not slot.identity_ids_present:
        return False
    if not slot.protagonist_matte_enabled:
        return False
    return True
