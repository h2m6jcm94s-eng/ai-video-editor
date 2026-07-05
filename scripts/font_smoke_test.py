#!/usr/bin/env python3
"""Font smoke test: verify bundled fonts exist and FFmpeg can render them."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "render-worker" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "shared-py" / "src"))

from render_worker.compiler import (
    _BUNDLED_FONT_DIR,
    _FONT_FILES,
    _FONT_NAME_ALIASES,
    _STYLE_PRESET_FONTS,
    _get_fontconfig_file,
)


def _ffmpeg_render_sample(font_path: Path) -> bool:
    """Render one frame with the given font to confirm FFmpeg can load it."""
    if not shutil.which("ffmpeg"):
        return True  # skip render check if ffmpeg is unavailable
    with tempfile.TemporaryDirectory(prefix="ave_font_smoke_") as tmp:
        tmp_path = Path(tmp)
        # Copy font into the temp dir and reference by basename to avoid
        # Windows drive-colon issues in FFmpeg drawtext paths.
        local_font = tmp_path / font_path.name
        shutil.copy2(font_path, local_font)
        out = tmp_path / "frame.png"
        env = os.environ.copy()
        fc = _get_fontconfig_file()
        if fc and not env.get("FONTCONFIG_FILE"):
            env["FONTCONFIG_FILE"] = fc
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=1",
            "-vf",
            f"drawtext=fontfile={local_font.name}:text='ABC 123':fontsize=48:fontcolor=white:x=(w-tw)/2:y=(h-th)/2",
            "-frames:v",
            "1",
            str(out),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, cwd=tmp, env=env, timeout=30)
        except Exception:
            return False
        return r.returncode == 0 and out.exists() and out.stat().st_size > 0


def main() -> int:
    failures = 0
    families = set(_FONT_FILES)
    for presets in _STYLE_PRESET_FONTS.values():
        families.update(presets)
    families.update(_FONT_NAME_ALIASES.values())

    print(f"Bundled font dir: {_BUNDLED_FONT_DIR}")
    for family in sorted(families):
        filename = _FONT_FILES.get(family)
        if not filename:
            print(f"  [FAIL] {family}: not registered in _FONT_FILES")
            failures += 1
            continue
        path = Path(_BUNDLED_FONT_DIR) / filename
        exists = path.exists()
        renders = _ffmpeg_render_sample(path) if exists else False
        status = "PASS" if exists and renders else "FAIL"
        print(f"  [{status}] {family}: {path.name} exists={exists} renders={renders}")
        if not (exists and renders):
            failures += 1

    for alias, target in sorted(_FONT_NAME_ALIASES.items()):
        filename = _FONT_FILES.get(target)
        ok = bool(filename and (Path(_BUNDLED_FONT_DIR) / filename).exists())
        print(f"  [{'PASS' if ok else 'FAIL'}] alias {alias} -> {target}")
        if not ok:
            failures += 1

    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
