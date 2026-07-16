# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""HM-MVGD-HM stylised colour-transfer filter primitive.

The real algorithm is histogram matching + multivariate Gaussian distribution
+ histogram matching.  FFmpeg has no native implementation, so we approximate
its look with a chained saturation/contrast/white-balance adjustment enabled
over the effect window.
"""

from __future__ import annotations


def hm_mvgd_hm_filter(
    rel_start: float,
    rel_end: float,
    strength: float = 0.5,
    warmth: float = 0.0,
    tint: float = 0.0,
) -> str:
    """Return an FFmpeg filter that applies a stylised colour grade.

    ``strength`` controls saturation/contrast intensity, ``warmth`` biases the
    shadows toward warm/cool, and ``tint`` biases toward green/magenta.
    """
    saturation = 1.0 + strength * 0.4
    contrast = 1.0 + strength * 0.15
    brightness = -strength * 0.03
    # Map warmth/tint to colorbalance values in [-1, 1] range accepted by FFmpeg.
    red_shadows = max(-1.0, min(1.0, warmth))
    blue_shadows = max(-1.0, min(1.0, -warmth))
    green_shadows = max(-1.0, min(1.0, -tint))
    magenta_shadows = max(-1.0, min(1.0, tint))
    enable = f"between(t\\,{rel_start:.3f}\\,{rel_end:.3f})"
    return (
        f"eq=saturation={saturation}:contrast={contrast}:brightness={brightness}:"
        f"enable='{enable}',"
        f"colorbalance=rs={red_shadows}:bs={blue_shadows}:gs={green_shadows}:"
        f"rm={magenta_shadows}:bm={-magenta_shadows}:gm={-green_shadows}:"
        f"enable='{enable}'"
    )
