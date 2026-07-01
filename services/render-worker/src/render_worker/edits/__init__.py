# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Targeted object-editing tiers for the render pipeline.

Each module implements one intent bucket returned by
``reason_worker.edit_intent.classify_edit_intent``:

* ``color_shift``      – hue/saturation/value tweaks constrained to a mask.
* ``texture_replace``  – generative inpaint of a masked region.
* ``structural_change`` – heavy generative edits requiring anchor frames and approval.
"""

from __future__ import annotations

from render_worker.edits.color_shift import apply_color_shift_tier
from render_worker.edits.structural_change import apply_structural_change_tier
from render_worker.edits.texture_replace import apply_texture_replace_tier

__all__ = [
    "apply_color_shift_tier",
    "apply_texture_replace_tier",
    "apply_structural_change_tier",
]
