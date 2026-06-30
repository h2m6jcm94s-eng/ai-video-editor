# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Orchestrator for targeted object generation and editing."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from reason_worker.edit_intent import (
    EDIT_INTENT_LABELS,
    classify_edit_intent,
    is_brand_ip_violation,
    is_face_edit,
)

from render_worker.edits import (
    apply_color_shift_tier,
    apply_structural_change_tier,
    apply_texture_replace_tier,
)
from render_worker.sam3_client import (
    Sam3UnavailableError,
    SegmentationResult,
    segment_object_in_clip,
)

logger = logging.getLogger(__name__)

# Placeholder monthly budget for generative object edits. In production this
# should be read from a persistent billing/usage store.
MONTHLY_GENERATION_BUDGET_USD = float(os.environ.get("MONTHLY_GENERATION_BUDGET_USD", "5.0"))

TIER_COST_USD = {
    "color_shift": 0.05,
    "texture_replace": 0.50,
    "structural_change": 2.00,
}


@dataclass
class ObjectEditResult:
    """Result returned by ``run_object_edit``.

    Attributes:
        output_path: Path to the rendered video (or the input clip if the edit
            was skipped).
        tier: Intent tier dispatched to.
        cost_usd: Estimated cost of the edit in USD.
        skipped: True when the edit was gated/skipped rather than rendered.
        skip_reason: Human-readable reason when ``skipped`` is True.
        mask_result: Optional SAM3 segmentation result.
    """

    output_path: str
    tier: str
    cost_usd: float
    skipped: bool = False
    skip_reason: Optional[str] = None
    mask_result: Optional[SegmentationResult] = None


def _check_generation_budget(tier: str, current_spend: float) -> None:
    """Placeholder budget gate.

    TODO: Replace with a real usage store keyed by project/user/month.
    """
    cost = TIER_COST_USD.get(tier, 0.0)
    if current_spend + cost > MONTHLY_GENERATION_BUDGET_USD:
        raise RuntimeError(
            f"Monthly generative edit budget exceeded: "
            f"${current_spend:.2f} spent + ${cost:.2f} requested > "
            f"${MONTHLY_GENERATION_BUDGET_USD:.2f}"
        )


def _ethics_gates(
    prompt: str,
    mask_result: SegmentationResult,
    tier: str,
) -> Optional[str]:
    """Run brand/IP and face-edit ethics gates before generation.

    Returns a skip reason string if the edit should be blocked, otherwise None.
    """
    try:
        if is_brand_ip_violation(prompt):
            return "Edit blocked by brand/IP policy"
    except Exception as exc:
        logger.warning("Brand/IP gate failed for prompt %r: %s", prompt, exc)

    # Face-edit gate requires a frame and mediapipe; skip when the gate cannot
    # be evaluated rather than block all face-adjacent edits.
    if tier in {"texture_replace", "structural_change"}:
        try:
            # The function raises NotImplementedError when mediapipe is missing.
            # We pass the first mask as a stand-in frame for the gate check.
            first_mask = mask_result.masks[0] if mask_result.masks else None
            if first_mask is not None and is_face_edit(first_mask, first_mask):
                return "Face edit requires explicit user consent"
        except NotImplementedError:
            logger.info("Face-edit gate not available (mediapipe missing); continuing")
        except Exception as exc:
            logger.warning("Face-edit gate failed: %s", exc)

    return None


def _select_mask_for_tier(mask_result: SegmentationResult) -> Any:
    """Normalize SAM3 masks into the contract each tier expects.

    TODO: Once SAM3 returns per-frame image paths or a mask video path, update
    this helper to return the appropriate representation.
    """
    return mask_result.masks


async def run_object_edit(
    clip_path: str,
    prompt: str,
    prompt_type: str = "text",
    *,
    current_monthly_spend: float = 0.0,
) -> ObjectEditResult:
    """Run a targeted object edit on ``clip_path`` driven by ``prompt``.

    Args:
        clip_path: Path to the source video clip.
        prompt: Text, box, or point prompt describing the object to edit.
        prompt_type: ``text`` | ``box`` | ``point``.
        current_monthly_spend: Already-spent generative budget this month.

    Returns:
        An ``ObjectEditResult`` describing the rendered output and cost.
    """
    # 1. Segment the object with SAM3.
    try:
        mask_result = await segment_object_in_clip(clip_path, prompt, prompt_type=prompt_type)
    except Sam3UnavailableError:
        logger.warning("SAM3 unavailable for object edit on %s; skipping", clip_path)
        return ObjectEditResult(
            output_path=clip_path,
            tier="unknown",
            cost_usd=0.0,
            skipped=True,
            skip_reason="SAM3 server unavailable",
        )

    if not mask_result.masks:
        return ObjectEditResult(
            output_path=clip_path,
            tier="unknown",
            cost_usd=0.0,
            skipped=True,
            skip_reason="SAM3 produced no masks",
            mask_result=mask_result,
        )

    # 2. Classify edit intent.
    if prompt_type == "text":
        tier = classify_edit_intent(prompt)
    else:
        # Non-text prompts default to the most conservative tier.
        tier = "structural_change"

    if tier not in EDIT_INTENT_LABELS:
        tier = "structural_change"

    # 3. Budget gate.
    _check_generation_budget(tier, current_monthly_spend)

    # 4. Ethics gates.
    skip_reason = _ethics_gates(prompt, mask_result, tier)
    if skip_reason:
        return ObjectEditResult(
            output_path=clip_path,
            tier=tier,
            cost_usd=0.0,
            skipped=True,
            skip_reason=skip_reason,
            mask_result=mask_result,
        )

    # 5. Dispatch to tier.
    mask_input = _select_mask_for_tier(mask_result)
    cost = TIER_COST_USD.get(tier, 0.0)

    if tier == "color_shift":
        output_path = apply_color_shift_tier(clip_path, mask_input, {"hue": 15.0})
    elif tier == "texture_replace":
        output_path = await apply_texture_replace_tier(clip_path, mask_input, prompt)
    else:  # structural_change
        output_path = await apply_structural_change_tier(clip_path, mask_input, prompt)

    return ObjectEditResult(
        output_path=output_path,
        tier=tier,
        cost_usd=cost,
        mask_result=mask_result,
    )
