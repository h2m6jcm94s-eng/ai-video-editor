// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import type { Overlay } from "@/types/api";

interface TextOverlayProps {
  overlay: Overlay;
}

export function TextOverlay({ overlay }: TextOverlayProps) {
  return (
    <div
      className="absolute flex items-center justify-center text-center drop-shadow-md"
      style={{
        left: `${overlay.x}%`,
        top: `${overlay.y}%`,
        width: `${overlay.width}%`,
        height: `${overlay.height}%`,
        color: (overlay.style?.color as string) || "white",
        fontSize: `${(overlay.style?.fontSize as number) || 48}px`,
        fontFamily: (overlay.style?.fontFamily as string) || "Inter, sans-serif",
        textAlign: ((overlay.style?.align as string) || "center") as React.CSSProperties["textAlign"],
        textShadow: "0 2px 4px rgba(0,0,0,0.5)",
      }}
    >
      {overlay.text}
    </div>
  );
}
