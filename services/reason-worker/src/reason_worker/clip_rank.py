# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Rank user clips for each slot using weighted scoring + diversity."""

from typing import List, Dict, Optional
import numpy as np

from shared_py.models import Slot, ClipScore


def _slot_query_text(slot: Slot) -> str:
    """Build a natural-language search query from slot intent."""
    parts = [
        slot.target_shot_type,
        slot.subject_hint,
        slot.motion_hint,
        f"energy {slot.energy_level:.1f}",
    ]
    if slot.required_tags:
        parts.append(" ".join(slot.required_tags))
    return ", ".join(p for p in parts if p)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity in [-1, 1]."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _semantic_score(
    slot: Slot,
    clip_id: str,
    embeddings: Dict[str, np.ndarray],
    slot_embeddings: Dict[int, np.ndarray],
) -> float:
    """Return a semantic score for a clip against a slot.

    Uses Marengo text-to-video cosine similarity when both slot text and clip
    video embeddings are available; otherwise falls back to the legacy default.
    The similarity is rescaled from [-1, 1] to [0, 1] for the weighted total.
    """
    slot_emb = slot_embeddings.get(slot.index)
    clip_emb = embeddings.get(clip_id)
    if slot_emb is not None and clip_emb is not None:
        return 0.5 + 0.5 * _cosine_similarity(slot_emb, clip_emb)
    return 0.7


def rank_clips_for_slots(
    slots: List[Slot],
    clip_metadata: Dict[str, dict],
    embeddings: Dict[str, np.ndarray] = None,
    marengo_client=None,
) -> Dict[int, List[ClipScore]]:
    """Rank clips for each slot using weighted scoring.

    Args:
        slots: Cut-list slots to rank clips for.
        clip_metadata: Mapping of clip_id to metadata dict with keys such as
            ``shot_type``, ``aesthetic_score``, ``motion_energy``, ``duration_sec``.
        embeddings: Optional precomputed video embeddings keyed by clip_id.
        marengo_client: Optional ``MarengoClient`` for generating slot text
            embeddings. When provided and available, semantic scores become
            text-to-video cosine similarities instead of the default heuristic.
    """
    embeddings = embeddings or {}
    rankings = {}
    chosen_embeddings = []
    chosen_clip_ids = []

    # Precompute slot text embeddings via Marengo when available.
    slot_embeddings: Dict[int, np.ndarray] = {}
    if marengo_client is not None and marengo_client.available():
        for slot in slots:
            query = _slot_query_text(slot)
            emb = marengo_client.embed_text(query)
            if emb is not None:
                slot_embeddings[slot.index] = emb

    for slot in slots:
        scores = []
        for clip_id, meta in clip_metadata.items():
            # Semantic score: real cosine similarity when Marengo is wired.
            semantic = _semantic_score(slot, clip_id, embeddings, slot_embeddings)

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
                similarities = []
                for ce in chosen_embeddings:
                    similarities.append(float(_cosine_similarity(emb, ce)))
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
            # Compare top choice against 4th choice for a more conservative gap
            gap = scores[0].total_score - scores[3].total_score
            confidences[slot_idx] = min(0.99, gap * 1.5)
        elif len(scores) > 1:
            gap = scores[0].total_score - scores[-1].total_score
            confidences[slot_idx] = min(1.0, gap * 2.0)
        else:
            confidences[slot_idx] = 0.5
    return confidences
