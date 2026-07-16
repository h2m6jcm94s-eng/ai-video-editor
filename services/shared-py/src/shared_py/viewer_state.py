# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""ViewerState model, Operation Ledger, and simulator for trajectory-based editing.

The ledger maps every editing verb/operation to its predicted effect on the
viewer: attention, arousal, valence, tension, and cognitive load.  The
simulator evolves these states forward in time so the composer can choose
verbs that steer the viewer toward a target trajectory.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from shared_py.models import BaseModelCamel


class ViewerState(BaseModelCamel):
    """A snapshot of predicted viewer state at a single moment."""

    attention: float = Field(default=0.5, ge=0.0, le=1.0)
    arousal: float = Field(default=0.5, ge=0.0, le=1.0)
    valence: float = Field(default=0.5, ge=0.0, le=1.0)
    tension: float = Field(default=0.0, ge=0.0, le=1.0)
    load: float = Field(default=0.0, ge=0.0, le=1.0)


class OperationEffect(BaseModelCamel):
    """Predicted delta an operation applies to ViewerState over its duration."""

    d_attention: float = Field(default=0.0, ge=-1.0, le=1.0)
    d_arousal: float = Field(default=0.0, ge=-1.0, le=1.0)
    d_valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    d_tension: float = Field(default=0.0, ge=-1.0, le=1.0)
    d_load: float = Field(default=0.0, ge=-1.0, le=1.0)
    novelty_family: str = ""
    duration_s: float = Field(default=0.0, ge=0.0)
    description: str = ""


class RegisteredOperation(BaseModelCamel):
    """A verb registered in the Operation Ledger."""

    id: str
    category: str
    params_schema: Dict[str, Any] = Field(default_factory=dict)
    prerequisites: List[str] = Field(default_factory=list)
    effect: OperationEffect = Field(default_factory=OperationEffect)


class OperationLedger:
    """Deterministic registry of editing verbs and their ViewerState effects."""

    def __init__(self) -> None:
        self._ops: Dict[str, RegisteredOperation] = {}

    def register(self, operation: RegisteredOperation) -> RegisteredOperation:
        if operation.id in self._ops:
            raise ValueError(f"Operation '{operation.id}' is already registered")
        self._ops[operation.id] = operation
        return operation

    def get(self, op_id: str) -> Optional[RegisteredOperation]:
        return self._ops.get(op_id)

    def list_ids(self) -> List[str]:
        return list(self._ops.keys())

    def list_by_category(self, category: str) -> List[RegisteredOperation]:
        return [op for op in self._ops.values() if op.category == category]


class ViewerStateSimulator:
    """Evolve ViewerState through a sequence of operations.

    State variables are clamped to [0, 1].  Deltas are scaled by a decay
    factor over the operation duration so short operations have less lasting
    impact than long ones.
    """

    def __init__(self, decay: float = 0.15) -> None:
        self.decay = decay
        self.ledger = OperationLedger()

    def apply(self, state: ViewerState, op_id: str, duration_s: float) -> ViewerState:
        op = self.ledger.get(op_id)
        if op is None:
            return state
        effect = op.effect
        effective_duration = max(effect.duration_s, duration_s)
        scale = 1.0 - self.decay * effective_duration
        scale = max(0.1, min(1.0, scale))
        return ViewerState(
            attention=self._clamp(state.attention + effect.d_attention * scale),
            arousal=self._clamp(state.arousal + effect.d_arousal * scale),
            valence=self._clamp(state.valence + effect.d_valence * scale),
            tension=self._clamp(state.tension + effect.d_tension * scale),
            load=self._clamp(state.load + effect.d_load * scale),
        )

    def simulate(
        self,
        initial: ViewerState,
        operations: List[tuple[str, float]],
    ) -> List[ViewerState]:
        """Return a trajectory given (op_id, duration_s) pairs."""
        trajectory = [initial]
        state = initial
        for op_id, duration_s in operations:
            state = self.apply(state, op_id, duration_s)
            trajectory.append(state)
        return trajectory

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))


def make_default_ledger() -> OperationLedger:
    """Return a ledger seeded with operations for existing effect verbs."""
    ledger = OperationLedger()

    # Camera / motion
    ledger.register(
        RegisteredOperation(
            id="zoom_in",
            category="camera",
            effect=OperationEffect(
                d_attention=0.15,
                d_arousal=0.1,
                d_tension=0.05,
                d_load=0.0,
                novelty_family="camera",
                duration_s=0.5,
                description="Push closer to subject; raises attention and arousal",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="zoom_out",
            category="camera",
            effect=OperationEffect(
                d_attention=0.05,
                d_arousal=-0.05,
                d_tension=-0.05,
                novelty_family="camera",
                duration_s=0.5,
                description="Pull back; releases tension slightly",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="pan_left",
            category="camera",
            effect=OperationEffect(
                d_attention=0.08,
                d_arousal=0.03,
                novelty_family="camera",
                duration_s=0.6,
                description="Horizontal camera pan",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="pan_right",
            category="camera",
            effect=OperationEffect(
                d_attention=0.08,
                d_arousal=0.03,
                novelty_family="camera",
                duration_s=0.6,
                description="Horizontal camera pan",
            ),
        )
    )

    # Effects
    ledger.register(
        RegisteredOperation(
            id="flash_frame",
            category="effect",
            effect=OperationEffect(
                d_attention=0.2,
                d_arousal=0.15,
                d_tension=0.1,
                novelty_family="stutter",
                duration_s=0.1,
                description="Single frame flash; high attention spike",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="shake",
            category="effect",
            effect=OperationEffect(
                d_attention=0.1,
                d_arousal=0.12,
                d_tension=0.08,
                d_load=0.05,
                novelty_family="motion",
                duration_s=0.3,
                description="Camera shake; adds energy and load",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="glitch",
            category="effect",
            effect=OperationEffect(
                d_attention=0.12,
                d_arousal=0.1,
                d_tension=0.1,
                d_load=0.08,
                novelty_family="stutter",
                duration_s=0.2,
                description="Digital glitch; raises arousal and load",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="vignette",
            category="effect",
            effect=OperationEffect(
                d_attention=0.05,
                d_arousal=-0.05,
                d_valence=-0.02,
                novelty_family="color",
                duration_s=0.5,
                description="Edge darkening; focuses attention inward",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="film_grain",
            category="effect",
            effect=OperationEffect(
                d_load=0.03,
                novelty_family="texture",
                duration_s=1.0,
                description="Film grain texture; low impact",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="color_pop",
            category="effect",
            effect=OperationEffect(
                d_attention=0.06,
                d_arousal=0.04,
                novelty_family="color",
                duration_s=0.5,
                description="Saturation boost; mild attention/arousal lift",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="chromatic_aberration",
            category="effect",
            effect=OperationEffect(
                d_attention=0.08,
                d_arousal=0.06,
                d_load=0.04,
                novelty_family="distortion",
                duration_s=0.3,
                description="RGB split; adds tension and load",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="hm_mvgd_hm",
            category="effect",
            effect=OperationEffect(
                d_attention=0.04,
                d_valence=0.03,
                novelty_family="color",
                duration_s=1.0,
                description="Heatmap-driven color move; gentle",
            ),
        )
    )

    # Transitions
    ledger.register(
        RegisteredOperation(
            id="hard_cut",
            category="transition",
            effect=OperationEffect(
                d_attention=0.1,
                d_tension=0.05,
                novelty_family="cut",
                duration_s=0.0,
                description="Instant cut; attention reset",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="fade",
            category="transition",
            effect=OperationEffect(
                d_attention=-0.05,
                d_arousal=-0.08,
                d_tension=-0.1,
                novelty_family="dissolve",
                duration_s=0.4,
                description="Fade; lowers arousal and tension",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="dissolve",
            category="transition",
            effect=OperationEffect(
                d_attention=-0.03,
                d_arousal=-0.05,
                d_tension=-0.08,
                novelty_family="dissolve",
                duration_s=0.5,
                description="Dissolve; gentle release",
            ),
        )
    )

    # Text
    ledger.register(
        RegisteredOperation(
            id="text_kinetic",
            category="text",
            effect=OperationEffect(
                d_attention=0.12,
                d_load=0.08,
                novelty_family="text",
                duration_s=1.0,
                description="Animated kinetic text; attention and load",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="lower_third",
            category="text",
            effect=OperationEffect(
                d_attention=0.06,
                d_load=0.05,
                novelty_family="text",
                duration_s=2.0,
                description="Lower third text; informative load",
            ),
        )
    )

    # S3 depth verbs (require depth analysis; render side uses SceneDepthAnalysis)
    ledger.register(
        RegisteredOperation(
            id="depth_push",
            category="camera",
            prerequisites=["depth"],
            effect=OperationEffect(
                d_attention=0.18,
                d_arousal=0.12,
                d_tension=0.08,
                novelty_family="camera",
                duration_s=0.8,
                description="Depth-aware push-in; stronger spatial emphasis",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="depth_parallax_left",
            category="camera",
            prerequisites=["depth"],
            effect=OperationEffect(
                d_attention=0.12,
                d_arousal=0.08,
                novelty_family="camera",
                duration_s=1.0,
                description="Parallax orbit left; depth-layer motion",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="depth_parallax_right",
            category="camera",
            prerequisites=["depth"],
            effect=OperationEffect(
                d_attention=0.12,
                d_arousal=0.08,
                novelty_family="camera",
                duration_s=1.0,
                description="Parallax orbit right; depth-layer motion",
            ),
        )
    )

    # S4 world text (depth-placed text)
    ledger.register(
        RegisteredOperation(
            id="world_text",
            category="text",
            prerequisites=["depth"],
            effect=OperationEffect(
                d_attention=0.1,
                d_load=0.08,
                novelty_family="text",
                duration_s=1.5,
                description="Text placed in world-space with depth cue",
            ),
        )
    )

    # Audio design (placeholders; T16.4 will refine)
    ledger.register(
        RegisteredOperation(
            id="riser",
            category="audio",
            effect=OperationEffect(
                d_tension=0.15,
                d_arousal=0.1,
                novelty_family="sound",
                duration_s=2.0,
                description="Rising sound effect; builds tension",
            ),
        )
    )
    ledger.register(
        RegisteredOperation(
            id="hit",
            category="audio",
            effect=OperationEffect(
                d_attention=0.2,
                d_tension=0.05,
                novelty_family="sound",
                duration_s=0.2,
                description="Percussive hit; punctuates moment",
            ),
        )
    )

    return ledger
