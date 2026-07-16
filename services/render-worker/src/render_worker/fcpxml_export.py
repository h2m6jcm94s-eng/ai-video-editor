# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""FCPXML exporter for the pro path (DaVinci Resolve) timeline hand-off.

Generates a Final Cut Pro XML 1.9 timeline from a ``CutList``. Resolve
reads this format natively, avoiding FFmpeg limitations around speed ramps,
cross dissolves, and layered compositing.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from shared_py.logging_config import StructuredLogger
from shared_py.models import CutList, Slot, RenderConfig, AudioTrack, Overlay

logger = StructuredLogger("render_worker.fcpxml_export")


def _s(seconds: float) -> str:
    """FCPXML time literal: decimal seconds followed by 's'."""
    return f"{float(seconds):.6f}s"


def _format_id(width: int, height: int, fps: float) -> str:
    return f"format_{width}x{height}_{int(fps)}fps"


def _unique_id(prefix: str, idx: int) -> str:
    return f"{prefix}-{idx}"


class FCPXMLBuilder:
    def __init__(self, cutlist: CutList, render_config: RenderConfig):
        self.cutlist = cutlist
        self.config = render_config or RenderConfig(output_path="output.mp4")
        self.fps = float(self.config.fps) or 30.0
        self.width = int(self.config.width)
        self.height = int(self.config.height)
        self.duration_s = self._sequence_duration()
        self.format_id = _format_id(self.width, self.height, self.fps)
        self._resource_idx = 0
        self.resources: Dict[str, ET.Element] = {}
        self.asset_ids: Dict[str, str] = {}

    def _sequence_duration(self) -> float:
        target = self.cutlist.globals.total_duration_s if self.cutlist.globals else 0.0
        if target:
            return float(target)
        if not self.cutlist.slots:
            return 0.0
        last = self.cutlist.slots[-1]
        return float(last.start_s + last.duration_s)

    def _next_resource_id(self, prefix: str = "r") -> str:
        self._resource_idx += 1
        return f"{prefix}{self._resource_idx}"

    def _get_or_create_asset(self, path: str) -> str:
        if path in self.asset_ids:
            return self.asset_ids[path]
        asset_id = self._next_resource_id("r")
        self.asset_ids[path] = asset_id
        p = Path(path)
        asset = ET.Element(
            "asset",
            {
                "id": asset_id,
                "name": p.name,
                "src": p.as_uri(),
                "start": "0s",
                "duration": _s(p.stat().st_size / 1_000_000) if p.exists() else _s(300),
                "hasVideo": "1",
                "hasAudio": "1",
            },
        )
        # Best-effort duration probe is not required for Resolve import; omit to
        # keep the exporter lightweight.
        self.resources[asset_id] = asset
        return asset_id

    def _add_title_effect_resource(self) -> str:
        """Add a Basic Title effect resource if not already present."""
        for rid, el in self.resources.items():
            if el.tag == "effect" and el.get("name") == "Basic Title":
                return rid
        rid = self._next_resource_id("r")
        effect = ET.Element(
            "effect",
            {
                "id": rid,
                "name": "Basic Title",
                "uid": " titles/Title/Basic Title",
            },
        )
        self.resources[rid] = effect
        return rid

    def _add_format_resource(self) -> None:
        fmt = ET.Element(
            "format",
            {
                "id": self.format_id,
                "name": f"FFVideoFormat{self.width}x{self.height}p{int(self.fps)}",
                "frameDuration": f"1/{int(self.fps)}s",
                "width": str(self.width),
                "height": str(self.height),
                "colorSpace": "Rec. 709",
            },
        )
        self.resources[self.format_id] = fmt

    def _build_time_map(self, slot: Slot) -> Optional[ET.Element]:
        """Build a timeMap element for the first speed_ramp effect on the slot."""
        ramp = next((e for e in slot.effects if e.type == "speed_ramp"), None)
        if ramp is None:
            return None
        params = ramp.params or {}
        start_speed = float(params.get("start_speed") or 1.0)
        end_speed = float(params.get("end_speed") or start_speed)
        avg_speed = max(0.1, (start_speed + end_speed) / 2.0)
        timeline_dur = float(slot.duration_s)
        source_dur = timeline_dur / avg_speed
        time_map = ET.Element("timeMap")
        ET.SubElement(
            time_map,
            "timept",
            {
                "time": "0s",
                "value": "0s",
                "interpolation": "linear",
            },
        )
        ET.SubElement(
            time_map,
            "timept",
            {
                "time": _s(timeline_dur),
                "value": _s(source_dur),
                "interpolation": "linear",
            },
        )
        return time_map

    def _build_clip(self, slot: Slot, clip_paths: Dict[str, str]) -> Optional[ET.Element]:
        clip_id = slot.selected_clip_id
        if not clip_id:
            return None
        path = clip_paths.get(clip_id)
        if not path:
            logger.warning("missing_clip_path", slot_index=slot.index, clip_id=clip_id)
            return None
        asset_id = self._get_or_create_asset(path)
        source_start = float(slot.source_window_start_s or 0.0)
        duration = float(slot.duration_s)
        clip = ET.Element(
            "clip",
            {
                "ref": asset_id,
                "name": clip_id,
                "offset": _s(slot.start_s),
                "start": _s(source_start),
                "duration": _s(duration),
            },
        )
        time_map = self._build_time_map(slot)
        if time_map is not None:
            clip.append(time_map)
        return clip

    def _transition_name(self, transition_in: str) -> Optional[str]:
        if transition_in in ("dissolve", "fade"):
            return "Cross Dissolve"
        if transition_in in ("whip",):
            # Resolve imports whips as built-in transitions if present; otherwise
            # falls back to a cut. We write the name and let Resolve substitute.
            return "Whip"
        return None

    def _build_spine(self, clip_paths: Dict[str, str]) -> ET.Element:
        spine = ET.Element("spine")
        prev_end = 0.0
        for slot in self.cutlist.slots:
            clip = self._build_clip(slot, clip_paths)
            if clip is None:
                continue

            # Insert a transition before this clip when the incoming transition
            # is not a hard cut. We place a half-duration overlap at the cut.
            transition_in = (slot.transition_in or "hard_cut").lower()
            trans_name = self._transition_name(transition_in)
            if trans_name and prev_end > 0:
                dur = 0.5
                offset = max(0.0, prev_end - dur / 2.0)
                transition = ET.Element(
                    "transition",
                    {
                        "name": trans_name,
                        "offset": _s(offset),
                        "duration": _s(dur),
                    },
                )
                spine.append(transition)

            spine.append(clip)
            prev_end = float(slot.start_s + slot.duration_s)
        return spine

    def _build_titles(self, clip_paths: Dict[str, str]) -> List[ET.Element]:
        """Return title elements as connected clips in lane 1."""
        title_rid = self._add_title_effect_resource()
        titles: List[ET.Element] = []
        for overlay in self.cutlist.overlays:
            title = ET.Element(
                "title",
                {
                    "ref": title_rid,
                    "name": overlay.text[:32],
                    "offset": _s(overlay.start_s),
                    "start": "0s",
                    "duration": _s(max(0.0, overlay.end_s - overlay.start_s)),
                    "lane": "1",
                },
            )
            text = ET.SubElement(title, "text")
            text_style = ET.SubElement(text, "text-style")
            text_style.text = overlay.text
            # Minimal style definition.
            ts_def = ET.SubElement(title, "text-style-def", {"id": _unique_id("ts", hash(overlay.text) % 100000)})
            ts = ET.SubElement(
                ts_def,
                "text-style",
                {
                    "font": overlay.font or "Arial",
                    "fontSize": str(overlay.font_size_px or 48),
                    "fontColor": overlay.color or "#FFFFFF",
                },
            )
            _ = ts
            titles.append(title)
        # Also emit kinetic text from slots as titles.
        for slot in self.cutlist.slots:
            if slot.kinetic_text:
                start = float(slot.start_s)
                dur = float(slot.duration_s)
                title = ET.Element(
                    "title",
                    {
                        "ref": title_rid,
                        "name": slot.kinetic_text[:32],
                        "offset": _s(start),
                        "start": "0s",
                        "duration": _s(dur),
                        "lane": "2",
                    },
                )
                text = ET.SubElement(title, "text")
                text_style = ET.SubElement(text, "text-style")
                text_style.text = slot.kinetic_text
                titles.append(title)
        return titles

    def _build_audio(self, song_path: Optional[str] = None) -> List[ET.Element]:
        """Return audio elements as connected clips in lane -1."""
        audio_elements: List[ET.Element] = []
        # First, use explicit audio tracks from the cutlist.
        for track in self.cutlist.audio_tracks:
            path = self.config.audio_paths.get(track.asset_id) if self.config.audio_paths else None
            if not path and track.role == "music" and song_path:
                path = song_path
            if not path:
                continue
            asset_id = self._get_or_create_asset(path)
            start = float(track.start_s)
            end = float(track.end_s)
            dur = max(0.0, end - start)
            audio = ET.Element(
                "audio",
                {
                    "ref": asset_id,
                    "name": track.role,
                    "offset": _s(start),
                    "start": _s(track.source_start_s or 0.0),
                    "duration": _s(dur),
                    "lane": "-1",
                    "role": track.role,
                },
            )
            audio_elements.append(audio)
        # Fallback: place the full song under the timeline if no tracks exist.
        if not audio_elements and song_path:
            asset_id = self._get_or_create_asset(song_path)
            audio = ET.Element(
                "audio",
                {
                    "ref": asset_id,
                    "name": "music",
                    "offset": "0s",
                    "start": "0s",
                    "duration": _s(self.duration_s),
                    "lane": "-1",
                    "role": "music",
                },
            )
            audio_elements.append(audio)
        return audio_elements

    def build(self, clip_paths: Dict[str, str], song_path: Optional[str] = None) -> ET.Element:
        self._add_format_resource()
        root = ET.Element("fcpxml", {"version": "1.9"})
        resources_el = ET.SubElement(root, "resources")
        # Add resources in deterministic order: format first, then assets/effects.
        if self.format_id in self.resources:
            resources_el.append(self.resources.pop(self.format_id))
        # Title effect needs to exist before titles reference it.
        self._add_title_effect_resource()
        for asset_id in sorted(self.resources):
            resources_el.append(self.resources[asset_id])

        library = ET.SubElement(root, "library")
        event = ET.SubElement(library, "event", {"name": "AI Render"})
        project = ET.SubElement(event, "project", {"name": "Edit"})
        sequence = ET.SubElement(
            project,
            "sequence",
            {
                "format": self.format_id,
                "duration": _s(self.duration_s),
                "tcStart": "0s",
                "tcFormat": "NDF",
            },
        )
        spine = self._build_spine(clip_paths)
        for title in self._build_titles(clip_paths):
            spine.append(title)
        for audio in self._build_audio(song_path):
            spine.append(audio)
        sequence.append(spine)
        return root


def export_cutlist_to_fcpxml(
    cutlist: CutList,
    output_path: str,
    clip_paths: Dict[str, str],
    render_config: Optional[RenderConfig] = None,
    song_path: Optional[str] = None,
) -> str:
    """Write an FCPXML timeline for Resolve and return the output path."""
    builder = FCPXMLBuilder(cutlist, render_config or RenderConfig(output_path=output_path))
    root = builder.build(clip_paths, song_path=song_path)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    logger.info("fcpxml_exported", path=output_path, duration_s=builder.duration_s, slots=len(cutlist.slots))
    return output_path
