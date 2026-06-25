# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Segmentation worker package.

Imports are lazy so the package can be loaded without SAM3 or CUDA being
available.  The heavy dependencies are only imported inside engine.py.
"""

from shared_py.logging_config import configure_logging

configure_logging(service_name="segment-worker")


def __getattr__(name):
    if name == "is_segmentation_available":
        from segment_worker.engine import is_segmentation_available
        return is_segmentation_available
    if name == "detect_subject_mask_image":
        from segment_worker.engine import detect_subject_mask_image
        return detect_subject_mask_image
    if name == "detect_subject_mask_video":
        from segment_worker.engine import detect_subject_mask_video
        return detect_subject_mask_video
    if name == "segment_subject":
        from segment_worker.activities import segment_subject
        return segment_subject
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
