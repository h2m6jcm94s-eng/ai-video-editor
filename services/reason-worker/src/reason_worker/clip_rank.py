# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Rank user clips for each slot using weighted scoring + diversity."""

from typing import List, Dict
import numpy as np

from shared_py.models import Slot, ClipScore


def rank_clips_for_slots(
    slots: List[Slot],
    clip_metadata: Dict[str, dict],
    embeddings: Dict[str, np.ndarray] = None,
) -> Dict[int, List[ClipScore]]:
    """Rank clips for each slot using weighted scoring."""
    rankings = {}
    chosen_embeddings = []
    chosen_clip_ids = []

    for slot in slots:
        scores = []
        for clip_id, meta in clip_metadata.items():
            # Semantic score (placeholder - would use Marengo embeddings)
            semantic = 0.7  # Default
            if embeddings and clip_id in embeddings:
                # Cosine similarity would go here
                semantic = 0.7

            # Shot type match
            shot_type_score = 1.0 if meta.get("shot_type") == slot.target_shot_type else 0.3

            # Aesthetic score (placeholder)
            aesthetic = meta.get("aesthetic_score", 0.5)

            # Motion score
            motion_score = 1.0 - abs(meta.get("motion_energy", 0.5) - slot.energy_level)

            # Duration score
            clip_dur = meta.get("duration_sec", 5.0)
            duration_diff = abs(clip_dur - slot.duration_s)
            duration_score = np.exp(-(duration_diff / max(slot.duration_s, 0.1)) ** 2 / 0.5)

            # Diversity penalty
            diversity = 0.0
            if embeddings and clip_id in embeddings and chosen_embeddings:
                emb = embeddings[clip_id]
                norm_emb = np.linalg.norm(emb)
                similarities = []
                for ce in chosen_embeddings:
                    norm_ce = np.linalg.norm(ce)
                    if norm_emb == 0 or norm_ce == 0:
                        similarities.append(0.0)
                    else:
                        similarities.append(float(np.dot(emb, ce) / (norm_emb * norm_ce)))
                diversity = max(similarities) if similarities else 0.0

            total = (
                0.40 * semantic
                + 0.20 * shot_type_score
                + 0.15 * aesthetic
                + 0.15 * motion_score
                + 0.10 * duration_score
                - 0.25 * diversity
            )

            scores.append(ClipScore(
                clip_id=clip_id,
                semantic_score=semantic,
                shot_type_score=shot_type_score,
                aesthetic_score=aesthetic,
                motion_score=motion_score,
                duration_score=duration_score,
                diversity_penalty=diversity,
                total_score=total,
            ))

        # Sort by total score descending
        scores.sort(key=lambda x: x.total_score, reverse=True)
        rankings[slot.index] = scores

        # Add top choice to chosen for diversity
        if scores:
            top = scores[0]
            chosen_clip_ids.append(top.clip_id)
            if embeddings and top.clip_id in embeddings:
                chosen_embeddings.append(embeddings[top.clip_id])

    return rankings


def select_top_k_per_slot(
    rankings: Dict[int, List[ClipScore]], k: int = 3
) -> Dict[int, List[str]]:
    """Select top-k clip IDs per slot."""
    return {
        slot_idx: [s.clip_id for s in scores[:k]]
        for slot_idx, scores in rankings.items()
    }


def compute_confidence(rankings: Dict[int, List[ClipScore]]) -> Dict[int, float]:
    """Compute confidence for each slot based on score gap."""
    confidences = {}
    for slot_idx, scores in rankings.items():
        if len(scores) >= 4:
            gap = scores[0].total_score - scores[3].total_score
            confidences[slot_idx] = min(1.0, gap * 2.0)
        elif len(scores) > 1:
            gap = scores[0].total_score - scores[-1].total_score
            confidences[slot_idx] = min(1.0, gap * 2.0)
        else:
            confidences[slot_idx] = 0.5
    return confidences
