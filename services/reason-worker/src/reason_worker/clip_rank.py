# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Rank user clips for each slot using weighted scoring + diversity."""

import math
import random
from typing import List, Dict, Optional, Tuple
import numpy as np

from shared_py.models import Slot, ClipScore
from shared_py.tuning import RANK, FLOW, ANTICIPATION
from reason_worker.momentum import compute_mean_flow_vector, momentum_coherence
from reason_worker.anticipation import precompute_clip_motion_curve, compute_anticipation_offset


MOMENTUM_WEIGHT = RANK.MOMENTUM_WEIGHT


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
        return RANK.COSINE_RESCALE_OFFSET + RANK.COSINE_RESCALE_SCALE * _cosine_similarity(slot_emb, clip_emb)
    return RANK.DEFAULT_SEMANTIC_SCORE


def _best_window(
    meta: dict,
    slot_duration_s: float,
    used_windows: Dict[str, List[float]],
    clip_id: str,
):
    """Pick the best usable heatmap window for a slot.

    Heatmap windows are clip-relative, so comparing them to the global slot
    timeline was meaningless. Instead we pick the highest-scoring window that
    leaves enough room for the full slot duration and has not already been used
    for this clip.
    """
    heatmap = meta.get("heatmap", [])
    if not heatmap:
        return None, 0.5, "still"

    clip_dur = meta.get("duration_sec", 5.0)

    def _window_score(window: dict) -> float:
        base = window.get("score", 0.0)
        # Penalise reusing the exact same window so repeated clips still vary.
        if window.get("start_s") in used_windows.get(clip_id, []):
            base -= RANK.WINDOW_REUSE_PENALTY
        return base

    used_starts = set(used_windows.get(clip_id, []))

    # Prefer windows that fit the slot duration and have not been used yet.
    candidates = [
        w for w in heatmap
        if w.get("start_s", 0.0) + slot_duration_s <= clip_dur + 0.1
        and w.get("start_s") not in used_starts
    ]
    # Fallback 1: any unused window, even if shorter than the slot duration.
    if not candidates:
        candidates = [w for w in heatmap if w.get("start_s") not in used_starts]
    # Fallback 2: reuse an already-used window (penalty will still apply).
    if not candidates:
        candidates = heatmap

    best = max(candidates, key=_window_score)
    return (
        best.get("start_s"),
        float(_window_score(best)),
        best.get("dominant_motion", "still"),
    )


def _score_clip(
    slot: Slot,
    clip_id: str,
    meta: dict,
    embeddings: Dict[str, np.ndarray],
    slot_embeddings: Dict[int, np.ndarray],
    chosen_embeddings: List[np.ndarray],
    repeat_count: int = 0,
    exhaust_bonus: float = 0.0,
    used_windows: Optional[Dict[str, List[float]]] = None,
    last_chosen_clip_id: Optional[str] = None,
    at_usage_cap: bool = False,
) -> ClipScore:
    """Compute a single ClipScore for a slot/clip pair.

    Applies a repetition penalty so that clips already chosen for previous
    slots are less likely to win again, even when no embeddings are available.
    The ``exhaust_bonus`` rewards using clips that have not been used yet.
    """
    semantic = _semantic_score(slot, clip_id, embeddings, slot_embeddings)
    shot_type_score = 1.0 if meta.get("shot_type") == slot.target_shot_type else 0.3
    aesthetic = meta.get("aesthetic_score", 0.5)
    motion_score = 1.0 - abs(meta.get("motion_energy", 0.5) - slot.energy_level)
    clip_dur = meta.get("duration_sec", 5.0)
    duration_diff = abs(clip_dur - slot.duration_s)
    duration_score = np.exp(-(duration_diff / max(slot.duration_s, 0.1)) ** 2 / RANK.DURATION_SCORE_DIVISOR)

    used_windows = used_windows or {}
    window_start_s, window_score, dominant_motion = _best_window(
        meta, slot.duration_s, used_windows, clip_id
    )

    diversity = 0.0
    if embeddings and clip_id in embeddings and chosen_embeddings:
        emb = embeddings[clip_id]
        similarities = [float(_cosine_similarity(emb, ce)) for ce in chosen_embeddings]
        diversity = max(similarities) if similarities else 0.0

    # Strong repetition penalty: grows with each prior selection and spikes if
    # the same clip was just used in the previous slot.
    repetition_penalty = RANK.REPEAT_BASE_PENALTY * repeat_count
    if last_chosen_clip_id == clip_id:
        repetition_penalty += RANK.LAST_REPEAT_PENALTY

    # Hard cap: once a clip has been used enough times, refuse to pick it again.
    if at_usage_cap:
        repetition_penalty += RANK.USAGE_CAP_PENALTY

    total = (
        RANK.SEMANTIC_WEIGHT * semantic
        + RANK.SHOT_TYPE_WEIGHT * shot_type_score
        + RANK.AESTHETIC_WEIGHT * aesthetic
        + RANK.MOTION_WEIGHT * motion_score
        + RANK.DURATION_WEIGHT * duration_score
        + RANK.WINDOW_WEIGHT * window_score
        - RANK.DIVERSITY_WEIGHT * diversity
        - repetition_penalty
        - exhaust_bonus
    )

    return ClipScore(
        clip_id=clip_id,
        semantic_score=semantic,
        shot_type_score=shot_type_score,
        aesthetic_score=aesthetic,
        motion_score=motion_score,
        duration_score=duration_score,
        window_score=window_score,
        window_start_s=window_start_s,
        dominant_motion=dominant_motion,
        diversity_penalty=diversity,
        repetition_penalty=repetition_penalty,
        total_score=total,
    )


def rerank_with_momentum(
    rankings: Dict[int, List[ClipScore]],
    slots: List[Slot],
    clip_metadata: Dict[str, dict],
    clip_paths: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[int, List[ClipScore]], Dict[int, str]]:
    """Re-rank candidates so incoming motion continues outgoing motion.

    Iterates slots in order, adding ``MOMENTUM_WEIGHT * momentum_coherence`` to
    each candidate's score.  A clip that is the same as the previous slot's
    chosen clip gets no momentum bonus, otherwise conservation of momentum
    would create a gravity well that keeps the edit on one clip.

    Returns the re-ranked dictionary and a mapping of slot index to the chosen
    clip ID.
    """
    if not clip_paths:
        chosen = {
            slot.index: rankings[slot.index][0].clip_id
            for slot in slots
            if rankings.get(slot.index)
        }
        return rankings, chosen

    # Track the clip chosen for the immediately previous slot so we can zero the
    # momentum bonus for the same clip (see PR #11 gravity-well fix).

    new_rankings: Dict[int, List[ClipScore]] = {}
    chosen_clip_ids: Dict[int, str] = {}
    prev_end_motion: Optional[Tuple[float, float]] = None
    prev_chosen_clip_id: Optional[str] = None

    for slot in slots:
        scores = rankings.get(slot.index, [])
        if not scores:
            new_rankings[slot.index] = []
            continue

        if prev_end_motion is None or prev_chosen_clip_id is None:
            new_rankings[slot.index] = scores
            top = scores[0]
        else:
            reranked: List[Tuple[ClipScore, float]] = []
            for score in scores:
                # Do not reward a clip for continuing itself; that causes
                # repeats. Momentum should only smooth transitions between
                # different clips.
                if score.clip_id == prev_chosen_clip_id:
                    bonus = 0.0
                else:
                    path = clip_paths.get(score.clip_id)
                    if path is None:
                        bonus = 0.0
                    else:
                        start_s = score.window_start_s if score.window_start_s is not None else slot.start_s
                        candidate_start_motion = compute_mean_flow_vector(path, start_s, n_frames=FLOW.N_FRAMES)
                        bonus = RANK.MOMENTUM_WEIGHT * momentum_coherence(
                            prev_end_motion, candidate_start_motion
                        )
                reranked.append((score, score.total_score + bonus))
            reranked.sort(key=lambda x: x[1], reverse=True)
            new_scores = [
                item[0].model_copy(update={"total_score": item[1]})
                for item in reranked
            ]
            new_rankings[slot.index] = new_scores
            top = new_scores[0]

        chosen_clip_ids[slot.index] = top.clip_id
        prev_chosen_clip_id = top.clip_id
        end_path = clip_paths.get(top.clip_id)
        if end_path is not None:
            end_s = (top.window_start_s if top.window_start_s is not None else slot.start_s) + slot.duration_s
            prev_end_motion = compute_mean_flow_vector(end_path, end_s, n_frames=FLOW.N_FRAMES)
        else:
            prev_end_motion = (0.0, 0.0)

    return new_rankings, chosen_clip_ids


def apply_anticipation_offsets(
    slots: List[Slot],
    chosen_clip_ids: Dict[int, str],
    clip_motion_curves: Dict[str, np.ndarray],
    fps: float = 24.0,
) -> None:
    """Set ``slot.anticipation_offset_s`` for each chosen clip.

    The offset shifts the source window start so the cut lands shortly before
    the dominant motion peak in the clip.
    """
    for slot in slots:
        clip_id = chosen_clip_ids.get(slot.index)
        if clip_id is None:
            continue
        curve = clip_motion_curves.get(clip_id)
        if curve is None or len(curve) == 0:
            continue
        source_start = slot.source_window_start_s
        if source_start is None:
            source_start = slot.start_s
        offset = compute_anticipation_offset(
            source_window_start_s=source_start,
            source_window_duration_s=slot.duration_s,
            clip_motion_curve=curve,
            fps=fps,
            target_offset_ms=333.0,
        )
        slot.anticipation_offset_s = offset


def rank_clips_for_slots(
    slots: List[Slot],
    clip_metadata: Dict[str, dict],
    embeddings: Dict[str, np.ndarray] = None,
    marengo_client=None,
    fallback_policy: str = "round_robin",
    force_exhaust: bool = True,
    clip_paths: Optional[Dict[str, str]] = None,
    use_momentum: bool = True,
    use_anticipation: bool = True,
    clip_order_fallback: str = "smart",
    clip_order_smart_threshold: float = 0.15,
) -> Dict[int, List[ClipScore]]:
    """Rank clips for each slot using weighted scoring.

    Args:
        slots: Cut-list slots to rank clips for.
        clip_metadata: Mapping of clip_id to metadata dict with keys such as
            ``shot_type``, ``aesthetic_score``, ``motion_energy``, ``duration_sec``.
        embeddings: Optional precomputed video embeddings keyed by clip_id.
        marengo_client: Optional ``MarengoClient`` for generating slot text
            embeddings. When provided and available, semantic scores become
            text-to-video cosine similarities instead of the legacy heuristic.
        fallback_policy: How to fill slots that receive no ranking. One of
            ``round_robin`` (cycle through available clips) or ``best_available``
            (reuse the globally highest-scoring clip). Empty rankings are left
            untouched when ``clip_metadata`` is empty.
        force_exhaust: When True and there are at least as many slots as clips,
            apply a large bonus to clips that have not been used yet so every
            clip is chosen at least once before any clip repeats.
        clip_paths: Optional mapping of clip_id to local video path. When
            provided alongside ``use_momentum``/``use_anticipation``, optical
            flow is used to improve continuity and cut timing.
        use_momentum: Whether to re-rank candidates using conservation of
            momentum. Requires ``clip_paths``.
        use_anticipation: Whether to compute anticipation offsets for chosen
            clips. Requires ``clip_paths``.
        clip_order_fallback: Tie-break mode when smart scores are within
            ``clip_order_smart_threshold``. One of ``smart`` (keep score order),
            ``filename`` (alphabetical), ``upload`` (upload time), or ``shuffle``
            (deterministic per-slot shuffle).
        clip_order_smart_threshold: If the gap between the top two scores is
            smaller than this, ``clip_order_fallback`` is applied.
    """
    embeddings = embeddings or {}
    rankings: Dict[int, List[ClipScore]] = {}
    chosen_embeddings: List[np.ndarray] = []
    chosen_clip_counts: Dict[str, int] = {}
    used_windows: Dict[str, List[float]] = {}

    num_clips = len(clip_metadata)
    num_slots = len(slots)
    apply_exhaust_bonus = force_exhaust and num_clips > 0
    # Allow a clip to be reused, but cap it so one high-scoring clip cannot
    # dominate the edit. If we have at least as many clips as slots, no clip
    # needs to repeat. Otherwise the cap is a small margin above fair share.
    if num_slots <= num_clips:
        usage_cap = 1
    else:
        usage_cap = max(
            2,
            math.ceil(
                (num_slots / max(num_clips, 1)) * RANK.USAGE_CAP_OVERFLOW_FACTOR
            ),
        )
    # When there are more slots than clips, force every clip to be used at least
    # once before any clip is allowed to repeat (PR #12).
    enforce_full_exhaust = force_exhaust and num_slots > num_clips

    # Precompute slot text embeddings via Marengo when available.
    slot_embeddings: Dict[int, np.ndarray] = {}
    if marengo_client is not None and marengo_client.available():
        for slot in slots:
            query = _slot_query_text(slot)
            emb = marengo_client.embed_text(query)
            if emb is not None:
                slot_embeddings[slot.index] = emb

    last_chosen_clip_id: Optional[str] = None
    for slot in slots:
        scores = []
        for clip_id, meta in clip_metadata.items():
            repeat_count = chosen_clip_counts.get(clip_id, 0)
            exhaust_bonus = 0.0
            if apply_exhaust_bonus:
                # Strong bonus for completely unused clips; moderate bonus for
                # clips used less than the fair share.
                fair_share = num_slots / num_clips
                if repeat_count == 0:
                    exhaust_bonus = RANK.EXHAUST_UNUSED_BONUS
                elif repeat_count < fair_share:
                    exhaust_bonus = RANK.EXHAUST_FAIR_BONUS
            all_used_once = len(chosen_clip_counts) >= num_clips
            at_cap = (enforce_full_exhaust and not all_used_once and repeat_count > 0) or (
                repeat_count >= usage_cap
            )
            scores.append(
                _score_clip(
                    slot,
                    clip_id,
                    meta,
                    embeddings,
                    slot_embeddings,
                    chosen_embeddings,
                    repeat_count=repeat_count,
                    exhaust_bonus=exhaust_bonus,
                    used_windows=used_windows,
                    last_chosen_clip_id=last_chosen_clip_id,
                    at_usage_cap=at_cap,
                )
            )

        # Sort by total score descending
        scores.sort(key=lambda x: x.total_score, reverse=True)

        # Deterministic tie-break when the top candidates are statistically tied.
        if (
            clip_order_fallback != "smart"
            and len(scores) >= 2
            and (scores[0].total_score - scores[1].total_score) < clip_order_smart_threshold
        ):
            if clip_order_fallback == "filename":
                scores.sort(key=lambda s: clip_metadata.get(s.clip_id, {}).get("filename", s.clip_id))
            elif clip_order_fallback == "upload":
                scores.sort(
                    key=lambda s: (
                        clip_metadata.get(s.clip_id, {}).get("uploaded_at") or 0,
                        s.clip_id,
                    )
                )
            elif clip_order_fallback == "shuffle":
                shuffled = list(scores)
                random.Random(slot.index).shuffle(shuffled)
                scores = shuffled

        rankings[slot.index] = scores

        # Add top choice to chosen for diversity and repetition tracking
        if scores:
            top = scores[0]
            chosen_clip_counts[top.clip_id] = chosen_clip_counts.get(top.clip_id, 0) + 1
            used_windows.setdefault(top.clip_id, []).append(top.window_start_s)
            last_chosen_clip_id = top.clip_id
            if embeddings and top.clip_id in embeddings:
                chosen_embeddings.append(embeddings[top.clip_id])

    # Fallback: ensure no slot is left without at least one candidate when clips exist.
    if clip_metadata:
        available_clip_ids = list(clip_metadata.keys())
        for slot in slots:
            if rankings.get(slot.index):
                continue
            if fallback_policy == "round_robin":
                fallback_id = available_clip_ids[slot.index % len(available_clip_ids)]
            elif fallback_policy == "best_available":
                all_scores = [s for scores in rankings.values() for s in scores]
                if all_scores:
                    fallback_id = max(all_scores, key=lambda s: s.total_score).clip_id
                else:
                    fallback_id = available_clip_ids[0]
            else:
                continue
            meta = clip_metadata[fallback_id]
            fallback_score = _score_clip(
                slot,
                fallback_id,
                meta,
                embeddings,
                slot_embeddings,
                chosen_embeddings,
                repeat_count=chosen_clip_counts.get(fallback_id, 0),
            )
            rankings[slot.index] = [fallback_score]

    # Conservation of momentum: prefer continuous motion across slots.
    chosen_clip_ids: Dict[int, str] = {}
    if clip_paths and use_momentum:
        rankings, chosen_clip_ids = rerank_with_momentum(
            rankings, slots, clip_metadata, clip_paths=clip_paths
        )
    else:
        for slot in slots:
            if rankings.get(slot.index):
                chosen_clip_ids[slot.index] = rankings[slot.index][0].clip_id

    # Anticipation cutting: shift starts so cuts land on motion peaks.
    if clip_paths and use_anticipation:
        clip_motion_curves: Dict[str, np.ndarray] = {}
        for clip_id in set(chosen_clip_ids.values()):
            path = clip_paths.get(clip_id)
            if path:
                clip_motion_curves[clip_id] = precompute_clip_motion_curve(
                    path, fps_sample=ANTICIPATION.FPS_SAMPLE
                )
        apply_anticipation_offsets(slots, chosen_clip_ids, clip_motion_curves, fps=24.0)

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
            confidences[slot_idx] = max(0.0, min(1.0, gap * RANK.CONFIDENCE_TOP4_MULTIPLIER))
        elif len(scores) > 1:
            gap = scores[0].total_score - scores[-1].total_score
            confidences[slot_idx] = max(0.0, min(1.0, gap * RANK.CONFIDENCE_TAIL_MULTIPLIER))
        else:
            confidences[slot_idx] = 0.5
    return confidences
