#!/usr/bin/env python3
# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Lightweight renderer for a generated cutlist: extracts slot segments and
# concatenates them with the song. Used to produce README demo results when the
# full compiler path hits edge-cases (e.g., very short slots).
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CLIP_MAP = {
    "clip_0": Path("E:/work/ai_video_editor/docs/assets/car-meet/clip-1.mp4"),
    "clip_1": Path("E:/work/ai_video_editor/docs/assets/car-meet/clip-2.mp4"),
    "clip_2": Path("E:/work/ai_video_editor/docs/assets/car-meet/clip-3.mp4"),
}
SONG = Path("E:/work/ai_video_editor/docs/assets/car-meet/song.mp3")
CUTLIST = Path("C:/Users/devay/AppData/Local/Temp/ai-video-editor/cutlist.json")
OUTPUT = Path("E:/work/ai_video_editor/docs/assets/car-meet/result.mp4")


def run(cmd, **kwargs):
    print("$", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def main():
    if not CUTLIST.exists():
        print(f"Cutlist not found: {CUTLIST}")
        sys.exit(1)

    cutlist = json.loads(CUTLIST.read_text(encoding="utf-8"))
    slots = cutlist.get("slots", [])

    with tempfile.TemporaryDirectory(prefix="ave-demo-") as tmp:
        tmp_path = Path(tmp)
        segments = []
        for slot in slots:
            clip_id = slot.get("selectedClipId")
            if not clip_id or clip_id not in CLIP_MAP:
                continue
            start = float(slot["startS"])
            duration = float(slot["durationS"])
            src = CLIP_MAP[clip_id]
            seg = tmp_path / f"slot_{slot['index']:03d}.mp4"
            run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(start),
                    "-t", str(duration),
                    "-i", str(src),
                    "-vf", "fps=30,scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-an", str(seg),
                ],
                capture_output=True,
            )
            segments.append(seg)

        if not segments:
            print("No segments produced")
            sys.exit(1)

        list_file = tmp_path / "segments.txt"
        list_file.write_text(
            "\n".join(f"file '{s.as_posix()}'" for s in segments),
            encoding="utf-8",
        )

        run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-i", str(SONG),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-shortest",
                str(OUTPUT),
            ],
            capture_output=True,
        )

    size = OUTPUT.stat().st_size
    print(f"Rendered {OUTPUT} ({size} bytes)")


if __name__ == "__main__":
    main()
