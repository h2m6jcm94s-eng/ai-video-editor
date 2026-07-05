"""Render Test Folder 2 (Your Name / Kimi No Nawa AMV).

Reuses the existing batch2-offline-render.py pipeline but points the input
paths at `test folder 2/` (Clips/ + RADWIMPS Sparkle + trailer reference).
Runs Whisper + Demucs + full T.9 semantic stack (whatever has landed so far).

Usage:
    .venv/Scripts/python.exe scripts/render_test_folder_2.py [any batch2 flags]

Notes:
  - First run does full ingest: heatmaps for 60 clips + song analysis (Whisper +
    Demucs + CLAP + Wav2Vec2 + music events + Gemma narrative + DINO + SigLIP +
    clip emotion). Expect 40-90 min end to end depending on cache warm state.
  - Cache dirs at E:\\ai-video-editor-storage\\ are keyed by song_hash + clip_id,
    so this render will NOT clobber the batch 2 caches.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "scripts" / "batch2-offline-render.py").read_text(encoding="utf-8")

# Point paths at test folder 2. Keep everything else identical.
REPLACEMENTS = [
    (
        'BATCH_DIR = repo_root / "test files" / "batch 2"',
        'BATCH_DIR = repo_root / "test folder 2"',
    ),
    (
        'REFERENCE_NAME = "I CRIED WHILE I MADE THIS VIDEO  CYBERPUNK - Li Ray【AMV】 (1080p, h264, youtube).mp4"',
        'REFERENCE_NAME = "スパークル [original ver.] -Your name. Music Video edition- 予告編 from new album「人間開花」初回盤DVD.mp4"',
    ),
    (
        'SONG_NAME = "Let You Down - Dawid Podsiadło.flac"',
        'SONG_NAME = "RADWIMPS - スパークル (original ver.) - Sparkle - (320 Kbps).mp3"',
    ),
    (
        'OUTPUT_DIR = repo_root / "test files" / "batch 2" / "output"',
        'OUTPUT_DIR = repo_root / "test folder 2" / "output"',
    ),
    (
        'clip_paths = sorted((BATCH_DIR / "clips").glob("*.mp4"))',
        'clip_paths = sorted((BATCH_DIR / "Clips").glob("*.mp4"))',
    ),
]

patched = SRC
for old, new in REPLACEMENTS:
    if old not in patched:
        raise RuntimeError(
            f"Could not find expected constant in batch2-offline-render.py: {old!r}\n"
            f"The upstream script may have changed. Re-sync render_test_folder_2.py."
        )
    patched = patched.replace(old, new)

# Ensure output dir exists so log-writing does not fail before ingest.
out_dir = REPO / "test folder 2" / "output"
out_dir.mkdir(parents=True, exist_ok=True)

# Execute the patched script with the current argv (so all batch2 flags work).
exec(compile(patched, str(REPO / "scripts" / "batch2-offline-render.py"), "exec"))
