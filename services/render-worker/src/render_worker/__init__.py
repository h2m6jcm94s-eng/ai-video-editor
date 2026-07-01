# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
from shared_py.logging_config import configure_logging

configure_logging(service_name="render-worker")

# Lazy imports to avoid loading heavy ML/FFmpeg dependencies on module init
# (important for Temporal workflow sandbox imports).
def __getattr__(name):
    if name == "compile_timeline":
        from render_worker.compiler import compile_timeline
        return compile_timeline
    if name == "render_preview":
        from render_worker.compiler import render_preview
        return render_preview
    if name == "build_identity_masks":
        from render_worker.identity_matte import build_identity_masks
        return build_identity_masks
    if name == "segment_object_in_clip":
        from render_worker.sam3_client import segment_object_in_clip
        return segment_object_in_clip
    if name == "run_object_edit":
        from render_worker.object_edit import run_object_edit
        return run_object_edit
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "compile_timeline",
    "render_preview",
    "build_identity_masks",
    "segment_object_in_clip",
    "run_object_edit",
]
