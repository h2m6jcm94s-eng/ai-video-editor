# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
from shared_py.logging_config import configure_logging

configure_logging(service_name="reason-worker")


# Lazy imports to avoid loading heavy ML dependencies on module init
def __getattr__(name):
    if name == "generate_cutlist":
        from reason_worker.cutlist_gen import generate_cutlist
        return generate_cutlist
    if name == "rank_clips_for_slots":
        from reason_worker.clip_rank import rank_clips_for_slots
        return rank_clips_for_slots
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
