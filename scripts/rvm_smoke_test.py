#!/usr/bin/env python3
"""Smoke test for RVM v2 video matting on a single Cyberpunk clip.

Usage:
    .venv/Scripts/python scripts/rvm_smoke_test.py \
        "test files/batch 2/clips/Cyberpunk Edgerunners - S01E05 (33).mp4" \
        "test files/batch 2/output/matte_smoke.mp4"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import torch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input video path")
    parser.add_argument("output", help="Output matte video path")
    parser.add_argument("--frames", type=int, default=60, help="Max frames to process")
    args = parser.parse_args()

    print("Loading RVM v2 mobilenetv3...")
    model = torch.hub.load(
        "PeterL1n/RobustVideoMatting",
        "mobilenetv3",
        pretrained=True,
        trust_repo=True,
    )
    model = model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    cap = cv2.VideoCapture(args.input)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # RVM expects divisible-by-4 resolution; downscale for CPU speed.
    proc_w = (width // 4) & ~3
    proc_h = (height // 4) & ~3

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(args.output, fourcc, fps, (proc_w, proc_h), isColor=False)

    rec = [None] * 4
    downsample_ratio = 0.25
    count = 0

    print(f"Processing up to {args.frames} frames at {proc_w}x{proc_h}...")
    while cap.isOpened() and count < args.frames:
        ok, frame = cap.read()
        if not ok:
            break
        # BGR -> RGB, resize, normalize to [0,1]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (proc_w, proc_h))
        tensor = (
            torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).float().div(255.0).to(device)
        )
        with torch.no_grad():
            fgr, pha, *rec = model(tensor, *rec, downsample_ratio)
        matte = (pha.squeeze().cpu().numpy() * 255).astype(np.uint8)
        out.write(matte)
        count += 1
        if count % 30 == 0:
            print(f"  {count} frames")

    cap.release()
    out.release()
    print(f"Wrote {count} matte frames to {args.output}")


if __name__ == "__main__":
    main()
