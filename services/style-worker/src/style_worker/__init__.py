# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
# Lazy imports to avoid loading heavy ML dependencies on module init
def __getattr__(name):
    if name == "extract_lut_from_reference":
        from style_worker.lut_extract import extract_lut_from_reference
        return extract_lut_from_reference
    if name == "classify_transitions":
        from style_worker.transition_type import classify_transitions
        return classify_transitions
    if name == "extract_text_overlays":
        from style_worker.text_extract import extract_text_overlays
        return extract_text_overlays
    if name == "analyze_camera_motion":
        from style_worker.camera_motion import analyze_camera_motion
        return analyze_camera_motion
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "extract_lut_from_reference",
    "classify_transitions",
    "extract_text_overlays",
    "analyze_camera_motion",
]
