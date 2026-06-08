// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useRef, useEffect } from "react";
import ReactPlayer from "react-player";
import { OverlayCanvas } from "../canvas/OverlayCanvas";
import type { Asset, Overlay, Subtitle, PreviewEffects } from "@/types/api";

interface PreviewPanelProps {
  assets: Asset[];
  currentTime: number;
  isPlaying: boolean;
  onTimeUpdate: (time: number) => void;
  overlays: Overlay[];
  subtitles?: Subtitle[];
  showSubtitles?: boolean;
  aspectRatio?: string;
  effects?: PreviewEffects;
}

const RATIO_MAP: Record<string, string> = {
  "9:16": "9 / 16",
  "4:5": "4 / 5",
  "1:1": "1 / 1",
  "16:9": "16 / 9",
};

export function PreviewPanel({ assets, currentTime, isPlaying, onTimeUpdate, overlays, subtitles, showSubtitles = true, aspectRatio = "9:16", effects }: PreviewPanelProps) {
  const playerRef = useRef<ReactPlayer>(null);
  const referenceAsset = assets.find((a) => a.type === "reference");
  const seekingRef = useRef(false);

  useEffect(() => {
    if (playerRef.current && !seekingRef.current) {
      const internal = playerRef.current.getInternalPlayer();
      if (internal && Math.abs(internal.currentTime - currentTime) > 0.5) {
        seekingRef.current = true;
        playerRef.current.seekTo(currentTime, "seconds");
        setTimeout(() => { seekingRef.current = false; }, 150);
      }
    }
  }, [currentTime]);

  const activeOverlays = overlays.filter(
    (o) => currentTime >= o.start_time && currentTime <= o.end_time
  );

  const activeSubtitle = showSubtitles && subtitles?.find(
    (s) => currentTime >= s.start_s && currentTime <= s.end_s
  );

  const ratioStyle = RATIO_MAP[aspectRatio] || "9 / 16";

  const filterStyle = effects
    ? `brightness(${effects.brightness ?? 1}) contrast(${effects.contrast ?? 1}) saturate(${effects.saturation ?? 1}) blur(${effects.blur ?? 0}px) sepia(${effects.sepia ?? 0}) hue-rotate(${effects.hueRotate ?? 0}deg)`
    : undefined;

  return (
    <div className="flex-1 bg-black relative flex items-center justify-center overflow-hidden">
      {referenceAsset?.storageUrl ? (
        <div
          className="relative h-full max-h-full"
          style={{ aspectRatio: ratioStyle }}
        >
          <ReactPlayer
            ref={playerRef}
            url={referenceAsset.storageUrl}
            playing={isPlaying}
            width="100%"
            height="100%"
            style={{ position: "absolute", top: 0, left: 0, filter: filterStyle }}
            onProgress={({ playedSeconds }) => {
              if (!seekingRef.current) onTimeUpdate(playedSeconds);
            }}
            progressInterval={100}
            config={{ file: { attributes: { crossOrigin: "anonymous" } } }}
          />
          <OverlayCanvas overlays={activeOverlays} />
          {activeSubtitle && (
            <div className="absolute bottom-12 left-0 right-0 flex justify-center pointer-events-none">
              <div className="bg-black/70 text-white text-sm px-4 py-1.5 rounded-lg max-w-[80%] text-center">
                {activeSubtitle.text}
              </div>
            </div>
          )}
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
