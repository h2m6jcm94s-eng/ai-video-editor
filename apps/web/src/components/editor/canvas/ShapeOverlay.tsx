// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import type { Overlay } from "@/types/api";

interface ShapeOverlayProps {
  overlay: Overlay;
}

export function ShapeOverlay({ overlay }: ShapeOverlayProps) {
  const shapeType = (overlay.style?.shape as string) || "rectangle";
  const color = (overlay.style?.color as string) || "rgba(255,255,255,0.3)";

  const baseStyle: React.CSSProperties = {
    position: "absolute",
    left: `${overlay.x}%`,
    top: `${overlay.y}%`,
    width: `${overlay.width}%`,
    height: `${overlay.height}%`,
    backgroundColor: color,
  };

  if (shapeType === "circle") {
    return (
      <div
        className="absolute rounded-full"
        style={{
          ...baseStyle,
          borderRadius: "50%",
        }}
      />
    );
  }

  if (shapeType === "arrow") {
    return (
      <div
        className="absolute flex items-center"
        style={{
          left: `${overlay.x}%`,
          top: `${overlay.y + overlay.height / 2}%`,
          width: `${overlay.width}%`,
          height: "4px",
          backgroundColor: color,
        }}
      >
        <div
          className="absolute right-0"
          style={{
            width: 0,
            height: 0,
            borderTop: "6px solid transparent",
            borderBottom: "6px solid transparent",
            borderLeft: `8px solid ${color}`,
            transform: "translateX(2px)",
          }}
        />
      </div>
    );
  }

  return <div className="absolute rounded" style={baseStyle} />;
}
