# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Canonical verb registry.

The Python registry is the single source of truth for every editing verb/effect
that exists in the system.  The TypeScript command parser consumes a generated
JSON export of this registry so the two stacks share the same verb list.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class VerbDefinition:
    """One canonical verb definition."""

    id: str
    category: str
    params_schema: Dict[str, Any] = field(default_factory=dict)
    prerequisites: List[str] = field(default_factory=list)
    ledger_ref: Optional[str] = None
    implemented: bool = False
    description: str = ""


class VerbRegistry:
    """Deterministic registry of editing verbs/effects."""

    def __init__(self) -> None:
        self._verbs: Dict[str, VerbDefinition] = {}

    def register(self, verb: VerbDefinition) -> VerbDefinition:
        if verb.id in self._verbs:
            raise ValueError(f"Verb '{verb.id}' is already registered")
        self._verbs[verb.id] = verb
        return verb

    def get(self, verb_id: str) -> Optional[VerbDefinition]:
        return self._verbs.get(verb_id)

    def list_ids(self) -> List[str]:
        return list(self._verbs.keys())

    def list_all(self) -> List[VerbDefinition]:
        return list(self._verbs.values())

    def list_implemented(self) -> List[VerbDefinition]:
        return [v for v in self._verbs.values() if v.implemented]

    def to_json(self) -> str:
        return json.dumps(
            [asdict(v) for v in self._verbs.values()], indent=2, ensure_ascii=False
        )

    def to_markdown(self) -> str:
        lines = [
            "# Verb Registry",
            "",
            "Canonical list of editing verbs/effects in the system.",
            "Generated from `services/shared-py/src/shared_py/verb_registry.py`.",
            "",
            "| Verb | Category | Implemented | Prerequisites | Ledger Ref | Description |",
            "|---|---|---|---|---|---|",
        ]
        for v in self._verbs.values():
            prereqs = ", ".join(v.prerequisites) or "—"
            ledger = v.ledger_ref or "—"
            lines.append(
                f"| `{v.id}` | {v.category} | {'yes' if v.implemented else 'no'} | "
                f"{prereqs} | {ledger} | {v.description} |"
            )
        lines.append("")
        return "\n".join(lines)


def _slot_index_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "slotIndex": {"type": "integer", "minimum": 0},
            "startS": {"type": "number", "minimum": 0},
            "durationS": {"type": "number", "minimum": 0.5},
        },
        "required": ["slotIndex"],
    }


def _effect_type_schema(effect_types: List[str]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "slotIndex": {"type": "integer", "minimum": 0},
            "effectType": {"type": "string", "enum": effect_types},
            "startS": {"type": "number", "minimum": 0},
            "durationS": {"type": "number", "minimum": 0},
        },
        "required": ["slotIndex"],
    }


def make_default_registry() -> VerbRegistry:
    """Return the registry seeded with every implemented verb/effect."""
    registry = VerbRegistry()

    # Command verbs implemented by the deterministic TypeScript parser.
    command_verbs = [
        VerbDefinition(
            id="trim_slot",
            category="edit",
            params_schema=_slot_index_schema(),
            implemented=True,
            description="Change the duration of a cutlist slot.",
        ),
        VerbDefinition(
            id="cut_slot",
            category="edit",
            params_schema=_slot_index_schema(),
            implemented=False,
            description="Split or remove a slot (planned).",
        ),
        VerbDefinition(
            id="set_transition",
            category="edit",
            params_schema={
                "type": "object",
                "properties": {
                    "slotIndex": {"type": "integer", "minimum": 0},
                    "transition": {
                        "type": "string",
                        "enum": ["hard_cut", "fade", "dissolve", "slide", "zoom"],
                    },
                },
                "required": ["transition"],
            },
            implemented=True,
            description="Set the outgoing transition for a slot or the default.",
        ),
        VerbDefinition(
            id="add_effect",
            category="edit",
            params_schema=_effect_type_schema(
                [
                    "zoom_punch_in",
                    "shake",
                    "glitch",
                    "vignette",
                    "film_grain",
                    "color_pop",
                    "chromatic_aberration",
                    "text_kinetic",
                    "lower_third",
                    "camera_motion",
                ]
            ),
            implemented=True,
            description="Add an effect to a slot.",
        ),
        VerbDefinition(
            id="add_text_overlay",
            category="edit",
            params_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": 200},
                    "startS": {"type": "number", "minimum": 0},
                    "durationS": {"type": "number", "minimum": 0.5},
                    "position": {"type": "string", "enum": ["center", "top", "bottom"]},
                },
                "required": ["text"],
            },
            implemented=True,
            description="Add a text overlay to the cutlist.",
        ),
        VerbDefinition(
            id="add_subtitle",
            category="edit",
            implemented=False,
            description="Add a subtitle track entry (planned).",
        ),
        VerbDefinition(
            id="set_color_grade",
            category="edit",
            implemented=False,
            description="Apply a color grade (planned).",
        ),
        VerbDefinition(
            id="zoom_in",
            category="edit",
            params_schema={"type": "object", "properties": {"slotIndex": {"type": "integer", "minimum": 0}}},
            implemented=True,
            ledger_ref="zoom_in",
            description="Shorthand for adding a zoom_punch_in effect.",
        ),
        VerbDefinition(
            id="apply_filter",
            category="edit",
            params_schema=_effect_type_schema(
                ["film_grain", "vignette", "glitch", "shake", "color_pop", "chromatic_aberration"]
            ),
            implemented=True,
            description="Apply a named filter to a slot.",
        ),
        VerbDefinition(
            id="reorder_slots",
            category="edit",
            implemented=False,
            description="Reorder slots in the cutlist (planned).",
        ),
        VerbDefinition(
            id="remove_overlay",
            category="edit",
            implemented=False,
            description="Remove an overlay by id (planned).",
        ),
        VerbDefinition(
            id="change_tempo",
            category="edit",
            params_schema={
                "type": "object",
                "properties": {"direction": {"type": "string", "enum": ["faster", "slower"]}},
                "required": ["direction"],
            },
            implemented=True,
            description="Request a tempo change (currently falls back to explanation).",
        ),
    ]
    for v in command_verbs:
        registry.register(v)

    # Effect verbs rendered by the render worker.
    effect_verbs = [
        ("zoom_punch_in", "effect", "Scale punch-in effect."),
        ("focus_pull", "effect", "Blur focus pull."),
        ("freeze_frame", "effect", "Hold a single frame."),
        ("speed_ramp", "effect", "Variable speed segment."),
        ("shake", "effect", "Camera shake.", "shake"),
        ("glitch", "effect", "Digital glitch.", "glitch"),
        ("vignette", "effect", "Edge darkening.", "vignette"),
        ("film_grain", "effect", "Film grain texture.", "film_grain"),
        ("color_pop", "effect", "Saturation boost.", "color_pop"),
        ("chromatic_aberration", "effect", "RGB split distortion.", "chromatic_aberration"),
        ("hm_mvgd_hm", "effect", "Heatmap-driven color move.", "hm_mvgd_hm"),
        ("flash_frame", "effect", "Single frame flash.", "flash_frame"),
        ("reframe", "effect", "Aspect-ratio reframe."),
        ("stabilize", "effect", "Motion stabilization."),
        ("text_kinetic", "effect", "Animated kinetic text.", "text_kinetic"),
        ("lower_third", "effect", "Lower third graphic.", "lower_third"),
        ("callout_arrow", "effect", "Arrow callout graphic."),
        ("whoosh_sfx", "audio", "Whoosh sound effect."),
        ("ding_sfx", "audio", "Ding sound effect."),
        ("record_scratch_sfx", "audio", "Record scratch sound effect."),
        ("camera_motion", "effect", "Preset or keyframe camera move."),
        ("depth_push", "effect", "Depth-aware push-in.", "depth_push", ["depth"]),
        ("depth_parallax_left", "effect", "Depth-aware parallax left.", "depth_parallax_left", ["depth"]),
        ("depth_parallax_right", "effect", "Depth-aware parallax right.", "depth_parallax_right", ["depth"]),
        ("world_text", "effect", "Text placed in world-space behind subject.", "world_text", ["depth"]),
    ]
    for item in effect_verbs:
        verb_id, category, description = item[0], item[1], item[2]
        ledger_ref = item[3] if len(item) > 3 else None
        prerequisites = item[4] if len(item) > 4 else []
        registry.register(
            VerbDefinition(
                id=verb_id,
                category=category,
                implemented=True,
                ledger_ref=ledger_ref,
                prerequisites=prerequisites,
                description=description,
            )
        )

    # Viewer-state ledger operations that are not direct edit verbs.
    ledger_only = [
        ("zoom_out", "camera", "Pull back; releases tension slightly."),
        ("pan_left", "camera", "Horizontal camera pan left."),
        ("pan_right", "camera", "Horizontal camera pan right."),
        ("hard_cut", "transition", "Instant cut; attention reset."),
        ("fade", "transition", "Fade; lowers arousal and tension."),
        ("dissolve", "transition", "Dissolve; gentle release."),
        ("riser", "audio", "Rising sound effect; builds tension."),
        ("hit", "audio", "Percussive hit; punctuates moment."),
    ]
    for verb_id, category, description in ledger_only:
        registry.register(
            VerbDefinition(
                id=verb_id,
                category=category,
                implemented=True,
                ledger_ref=verb_id,
                description=description,
            )
        )

    return registry


if __name__ == "__main__":
    # Convenience: regenerate artifacts when run directly.
    reg = make_default_registry()
    repo_root = Path(__file__).resolve().parents[4]
    json_path = repo_root / "packages" / "shared-types" / "src" / "verbs.generated.json"
    ts_path = repo_root / "packages" / "shared-types" / "src" / "verbs.generated.ts"
    md_path = repo_root / "VERBS.md"

    json_path.write_text(reg.to_json(), encoding="utf-8")
    md_path.write_text(reg.to_markdown(), encoding="utf-8")

    verb_ids = reg.list_ids()
    ts_content = (
        "// Generated by services/shared-py/src/shared_py/verb_registry.py\n"
        "// Do not edit manually.\n\n"
        f"export const EDIT_VERB = {json.dumps(verb_ids, indent=2)} as const;\n"
    )
    ts_path.write_text(ts_content, encoding="utf-8")
    print(f"Wrote {json_path}, {ts_path}, {md_path}")
