# Lazy imports to avoid loading heavy ML dependencies on module init
def __getattr__(name):
    if name == "probe_video":
        from ingest_worker.probe import probe_video
        return probe_video
    if name == "detect_shot_boundaries":
        from ingest_worker.shot_detect import detect_shot_boundaries
        return detect_shot_boundaries
    if name == "detect_beats":
        from ingest_worker.beat_detect import detect_beats
        return detect_beats
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["probe_video", "detect_shot_boundaries", "detect_beats"]
