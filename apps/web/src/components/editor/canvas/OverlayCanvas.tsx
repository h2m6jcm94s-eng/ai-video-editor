// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { TextOverlay } from "./TextOverlay";
import { ShapeOverlay } from "./ShapeOverlay";
import { EffectOverlay } from "./EffectOverlay";
import type { Overlay } from "@/types/api";

interface OverlayCanvasProps {
  overlays: Overlay[];
}

export function OverlayCanvas({ overlays }: OverlayCanvasProps) {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {overlays.map((overlay) => {
        if (overlay.type === "text") {
          return <TextOverlay key={overlay.id} overlay={overlay} />;
        }
        if (overlay.type === "shape") {
          return <ShapeOverlay key={overlay.id} overlay={overlay} />;
        }
        if (overlay.type === "effect") {
          return <EffectOverlay key={overlay.id} overlay={overlay} />;
        }
        return null;
      })}
    </div>
  );
}
