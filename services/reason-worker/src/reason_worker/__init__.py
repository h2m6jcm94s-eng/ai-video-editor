# Lazy imports to avoid loading heavy ML dependencies on module init
def __getattr__(name):
    if name == "generate_cutlist":
        from reason_worker.cutlist_gen import generate_cutlist
        return generate_cutlist
    if name == "rank_clips_for_slots":
        from reason_worker.clip_rank import rank_clips_for_slots
        return rank_clips_for_slots
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["generate_cutlist", "rank_clips_for_slots"]
