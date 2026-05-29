"""Extract LUT from reference video using color-matcher."""

import os
import tempfile
from typing import Optional, Tuple
import numpy as np
import cv2

try:
    from color_matcher import ColorMatcher
    from color_matcher.io_handler import load_img, save_img
    from color_matcher.normalizer import Normalizer
except ImportError:
    ColorMatcher = None

try:
    import colour
except ImportError:
    colour = None

from shared_py.models import StyleAnalysis


def sample_frames(video_path: str, n_samples: int = 50) -> list:
    """Sample n frames evenly across the video, skipping first/last 0.5s."""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    skip_frames = int(fps * 0.5)

    valid_range = (skip_frames, total_frames - skip_frames)
    indices = np.linspace(valid_range[0], valid_range[1], n_samples, dtype=int)

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            # Skip dark/letterboxed frames
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = gray.mean()
            if 15 < mean_brightness < 240:
                frames.append(frame)

    cap.release()
    return frames


def extract_lut_from_reference(
    video_path: str,
    output_dir: str,
    strength: float = 0.5,
) -> Tuple[Optional[str], StyleAnalysis]:
    """Extract a .cube LUT from reference video and return style analysis."""
    frames = sample_frames(video_path, n_samples=50)
    if len(frames) < 10:
        return None, StyleAnalysis(lut_extracted=False)

    # Build a "source" identity cube image for color matching
    # We'll use the median color palette as target
    # For actual color-matcher, we need source and target image pairs
    # Here we build a LUT by analyzing the color distribution

    if colour is None:
        return None, StyleAnalysis(lut_extracted=False)

    # Compute median frame as reference style
    median_frame = np.median(np.stack(frames), axis=0).astype(np.uint8)

    # Build 33x33x33 identity LUT
    lut_size = 33
    identity_lut = np.zeros((lut_size, lut_size, lut_size, 3), dtype=np.float32)
    for r in range(lut_size):
        for g in range(lut_size):
            for b in range(lut_size):
                identity_lut[r, g, b] = [
                    r / (lut_size - 1) * 255,
                    g / (lut_size - 1) * 255,
                    b / (lut_size - 1) * 255,
                ]

    # Apply color matching: fit reference colors to identity
    # Simplified approach: compute a color transformation from identity to reference palette
    # For production, use HM-MVGD-HM method from color-matcher

    # Compute color statistics
    frames_arr = np.stack(frames).reshape(-1, 3)
    # Sample subset for speed
    sample_idx = np.random.choice(len(frames_arr), min(100000, len(frames_arr)), replace=False)
    samples = frames_arr[sample_idx].astype(np.float32)

    mean_color = samples.mean(axis=0)
    std_color = samples.std(axis=0)

    # Build LUT by scaling identity colors toward reference statistics
    # This is a simplified Reinhard-style transfer
    identity_flat = identity_lut.reshape(-1, 3)
    # Normalize, scale, denormalize
    ref_mean = mean_color
    ref_std = std_color + 1e-6
    id_mean = 128.0
    id_std = 60.0

    transformed = ((identity_flat - id_mean) / id_std) * ref_std + ref_mean
    transformed = np.clip(transformed, 0, 255)
    lut_data = transformed.reshape(lut_size, lut_size, lut_size, 3).astype(np.float16)

    # Write .cube file
    os.makedirs(output_dir, exist_ok=True)
    cube_path = os.path.join(output_dir, "style.cube")

    with open(cube_path, "w") as f:
        f.write(f"TITLE \"Extracted from {os.path.basename(video_path)}\"\n")
        f.write(f"LUT_3D_SIZE {lut_size}\n")
        f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write("DOMAIN_MAX 1.0 1.0 1.0\n")
        for r in range(lut_size):
            for g in range(lut_size):
                for b in range(lut_size):
                    c = lut_data[r, g, b] / 255.0
                    f.write(f"{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}\n")

    # Compute color palette (top 5 dominant colors via k-means)
    from sklearn.cluster import KMeans
    kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
    kmeans.fit(samples)
    palette = [f"#{int(c[2]):02x}{int(c[1]):02x}{int(c[0]):02x}" for c in kmeans.cluster_centers_]

    analysis = StyleAnalysis(
        color_palette=palette,
        contrast_level=float(std_color.mean() / 60.0),
        saturation_level=float(cv2.cvtColor(median_frame, cv2.COLOR_BGR2HSV)[:, :, 1].mean() / 128.0),
        brightness_level=float(mean_color.mean() / 128.0),
        lut_extracted=True,
        lut_storage_key=cube_path,
    )

    return cube_path, analysis
