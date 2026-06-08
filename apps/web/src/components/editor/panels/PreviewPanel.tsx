// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useRef, useEffect } from "react";
import ReactPlayer from "react-player";
import { OverlayCanvas } from "../canvas/OverlayCanvas";
import type { Asset, Overlay } from "@/types/api";

interface PreviewPanelProps {
  assets: Asset[];
  currentTime: number;
  isPlaying: boolean;
  onTimeUpdate: (time: number) => void;
  overlays: Overlay[];
}

export function PreviewPanel({ assets, currentTime, isPlaying, onTimeUpdate, overlays }: PreviewPanelProps) {
  const playerRef = useRef<ReactPlayer>(null);
  const referenceAsset = assets.find((a) => a.type === "reference");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (playerRef.current) {
      const internalPlayer = playerRef.current.getInternalPlayer();
      if (internalPlayer && Math.abs(internalPlayer.currentTime - currentTime) > 0.5) {
        playerRef.current.seekTo(currentTime, "seconds");
      }
    }
  }, [currentTime]);

  const activeOverlays = overlays.filter(
    (o) => currentTime >= o.start_time && currentTime <= o.end_time
  );

  return (
    <div ref={containerRef} className="flex-1 bg-black relative flex items-center justify-center overflow-hidden">
      {referenceAsset?.storageUrl ? (
        <div className="relative w-full h-full max-w-4xl max-h-full">
          <ReactPlayer
            ref={playerRef}
            url={referenceAsset.storageUrl}
            playing={isPlaying}
            width="100%"
            height="100%"
            style={{ position: "absolute", top: 0, left: 0 }}
            onProgress={({ playedSeconds }) => onTimeUpdate(playedSeconds)}
            progressInterval={100}
            config={{ file: { attributes: { crossOrigin: "anonymous" } } }}
          />
          <OverlayCanvas overlays={activeOverlays} />
        </div>
      ) : (
        <div className="text-zinc-600 text-sm">Upload a reference video to preview</div>
      )}

      <div className="absolute bottom-3 left-3 text-xs font-mono text-zinc-400 bg-black/60 px-2 py-1 rounded">
        {formatTime(currentTime)}
      </div>
    </div>
  );
}

function formatTime(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  const ms = Math.floor((sec % 1) * 100);
  if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}:${ms.toString().padStart(2, "0")}`;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}:${ms.toString().padStart(2, "0")}`;
}
