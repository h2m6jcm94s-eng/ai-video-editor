# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Centralized tuning constants for the AI video editor pipeline.

Putting knobs in one place makes the codebase easier to tune, review, and keep
consistent across ranking, optical-flow, identity, and rendering modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class RankTuning:
    """Tuning knobs for ``reason_worker.clip_rank`` scoring."""

    # Momentum re-ranking.
    MOMENTUM_WEIGHT: float = 0.3

    # Score component weights in ``_score_clip``.  Sum == 1.0.
    SIGLIP_SEMANTIC_WEIGHT: float = 0.18
    EMOTION_MATCH_WEIGHT: float = 0.25
    MOOD_MOTION_WEIGHT: float = 0.12
    HEATMAP_WEIGHT: float = 0.15
    SHOT_TYPE_WEIGHT: float = 0.10
    AESTHETIC_WEIGHT: float = 0.08
    MOTION_ENERGY_WEIGHT: float = 0.05
    DURATION_MATCH_WEIGHT: float = 0.07

    # Backwards-compatible aliases for old weight names (deprecated).
    SEMANTIC_WEIGHT: float = SIGLIP_SEMANTIC_WEIGHT
    MOTION_WEIGHT: float = MOTION_ENERGY_WEIGHT
    DURATION_WEIGHT: float = DURATION_MATCH_WEIGHT
    WINDOW_WEIGHT: float = HEATMAP_WEIGHT
    DIVERSITY_WEIGHT: float = 0.40
    EMOTION_WEIGHT: float = EMOTION_MATCH_WEIGHT

    # Repetition penalties.
    REPEAT_BASE_PENALTY: float = 0.25
    LAST_REPEAT_PENALTY: float = 0.4
    USAGE_CAP_PENALTY: float = 10.0
    ARC_REPEAT_EXTRA_PENALTY: float = 0.6

    # Exhaust / usage cap.
    EXHAUST_UNUSED_BONUS: float = -1.5
    EXHAUST_FAIR_BONUS: float = -0.4
    USAGE_CAP_OVERFLOW_FACTOR: float = 1.2

    # Semantic fallback when no embeddings are available.
    DEFAULT_SEMANTIC_SCORE: float = 0.7
    # Rescale cosine similarity from [-1, 1] to [0, 1].
    COSINE_RESCALE_OFFSET: float = 0.5
    COSINE_RESCALE_SCALE: float = 0.5

    # Heatmap window reuse penalty so repeated clips still vary.
    WINDOW_REUSE_PENALTY: float = 0.5
    # Reject heatmap windows whose per-window motion is below the library-wide
    # Nth percentile, unless the slot explicitly calls for low energy.
    # The percentile is applied across ALL clip windows in the library so a
    # clip that is entirely static cannot pass its own low bar.
    WINDOW_MOTION_PERCENTILE: float = 0.05
    # Slots below this energy threshold are allowed to use very still windows.
    LOW_ENERGY_MOTION_THRESHOLD: float = 0.3
    # Penalty applied to the window score when the clip is shorter than the slot
    # and the compiler will have to pad/loop the segment.
    SHORT_CLIP_WINDOW_PENALTY: float = 0.5
    # Duration score Gaussian denominator.
    DURATION_SCORE_DIVISOR: float = 0.5

    # Confidence computation.
    CONFIDENCE_TOP4_MULTIPLIER: float = 1.5
    CONFIDENCE_TAIL_MULTIPLIER: float = 2.0


@dataclass(frozen=True)
class FlowTuning:
    """Shared optical-flow parameters for momentum and anticipation."""

    # Downscale frames before flow computation for speed.
    TARGET_SIZE: Tuple[int, int] = (256, 144)
    # Number of frames to average for a motion vector.
    N_FRAMES: int = 8

    # OpenCV Farneback parameters.
    PYR_SCALE: float = 0.5
    LEVELS: int = 3
    WINSIZE: int = 15
    ITERATIONS: int = 3
    POLY_N: int = 5
    POLY_SIGMA: float = 1.2
    FLAGS: int = 0


@dataclass(frozen=True)
class MomentumTuning:
    """Tuning for conservation-of-momentum scoring."""

    # Neutral / rescale values for the cosine coherence score.
    COHERENCE_NEUTRAL: float = 0.5
    COHERENCE_SCALE: float = 0.5


@dataclass(frozen=True)
class AnticipationTuning:
    """Tuning for anticipation cut timing."""

    # Frame sampling rate for the cached motion curve.
    FPS_SAMPLE: float = 8.0
    # Minimum peak prominence on a normalized motion curve.
    MIN_PROMINENCE: float = 0.3
    # Place the cut this many ms before the dominant motion peak.
    TARGET_OFFSET_MS: float = 333.0
    # Do not shift the source window start past ``duration - pad``.
    MAX_OFFSET_PAD_S: float = 0.05


@dataclass(frozen=True)
class IdentityTuning:
    """Tuning for identity clustering and matting."""

    # Face sampling rate used when building per-clip face caches.
    SAMPLE_FPS: float = 2.0
    # Number of protagonist identities to select.
    TOP_N: int = 2
    # DBSCAN clustering threshold (cosine distance).
    DBSCAN_EPS: float = 0.4
    # Minimum cluster size.
    DBSCAN_MIN_SAMPLES: int = 5


@dataclass(frozen=True)
class CompilerTuning:
    """Tuning for the FFmpeg render compiler."""

    # Output presets keyed by export preset name.
    PRESET_DIMENSIONS: Dict[str, Tuple[int, int]] = field(
        default_factory=lambda: {
            "youtube_16_9": (1920, 1080),
            "youtube_4k_16_9": (3840, 2160),
            "reels_9_16": (1080, 1920),
            "tiktok_9_16": (1080, 1920),
            "square_1_1": (1080, 1080),
            "preview_360p_16_9": (640, 360),
        }
    )

    # Quality profiles for offline / UI profile selection.
    QUALITY_PROFILES: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: {
            "preview": {"preset": "ultrafast", "crf": 28},
            "draft": {"preset": "veryfast", "crf": 23},
            "demo": {"preset": "medium", "crf": 19},
            "export": {"preset": "slow", "crf": 17},
            "archive": {"preset": "veryslow", "crf": 15},
        }
    )

    # Default dimensions by aspect ratio.
    ASPECT_RATIO_DIMENSIONS: Dict[str, Tuple[int, int]] = field(
        default_factory=lambda: {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "4:5": (1080, 1350),
            "1:1": (1080, 1080),
        }
    )

    # Default music bed level (dB).
    DEFAULT_MUSIC_GAIN_DB: float = -3.0

    # Dialogue extraction.
    DIALOGUE_FADE_MIN_S: float = 0.02

    # Silent placeholder audio.
    SILENCE_SAMPLE_RATE: int = 48000

    # Dialogue bus dynamics.
    DIALOGUE_BUS_GATE_THRESHOLD_DB: float = -50.0
    DIALOGUE_BUS_GATE_RATIO: float = 10.0
    DIALOGUE_BUS_GATE_ATTACK_MS: float = 20.0
    DIALOGUE_BUS_GATE_RELEASE_MS: float = 200.0

    DIALOGUE_BUS_COMP_THRESHOLD_DB: float = -18.0
    DIALOGUE_BUS_COMP_RATIO: float = 3.0
    DIALOGUE_BUS_COMP_ATTACK_MS: float = 5.0
    DIALOGUE_BUS_COMP_RELEASE_MS: float = 100.0

    # NVENC fallback CQ when CRF is missing or invalid.
    NVENC_DEFAULT_CQ: int = 20


RANK = RankTuning()
FLOW = FlowTuning()
MOMENTUM = MomentumTuning()
ANTICIPATION = AnticipationTuning()
IDENTITY = IdentityTuning()
COMPILER = CompilerTuning()
