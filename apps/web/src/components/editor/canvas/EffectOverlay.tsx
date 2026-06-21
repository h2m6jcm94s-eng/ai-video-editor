// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import type { CanvasOverlay } from "@/types/api";

interface EffectOverlayProps {
  overlay: CanvasOverlay;
}

export function EffectOverlay({ overlay }: EffectOverlayProps) {
  const effectType = (overlay.style?.effect as string) || "vignette";

  const fills: Record<string, string> = {
    vignette: "radial-gradient(circle, transparent 60%, rgba(0,0,0,0.4) 100%)",
    blur: "blur(4px)",
    glow: "radial-gradient(circle, rgba(255,200,100,0.2) 0%, transparent 70%)",
  };

  return (
    <div
      className="absolute pointer-events-none"
      style={{
        left: `${overlay.x}%`,
        top: `${overlay.y}%`,
        width: `${overlay.width}%`,
        height: `${overlay.height}%`,
        background: fills[effectType] || fills.vignette,
        filter: effectType === "blur" ? "blur(4px)" : undefined,
      }}
    />
  );
}
