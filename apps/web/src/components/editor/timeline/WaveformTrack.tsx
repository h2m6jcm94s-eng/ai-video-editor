// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";

interface WaveformTrackProps {
  url: string;
  currentTime: number;
  isPlaying: boolean;
  onTimeUpdate: (time: number) => void;
}

export function WaveformTrack({ url, currentTime, isPlaying, onTimeUpdate }: WaveformTrackProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wavesurferRef = useRef<WaveSurfer | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: "#3f3f46",
      progressColor: "#10b981",
      height: 40,
      cursorColor: "transparent",
      interact: true,
    });

    ws.load(url);
    ws.on("seeking", (time: number) => onTimeUpdate(time));
    wavesurferRef.current = ws;

    return () => {
      ws.destroy();
    };
  }, [url, onTimeUpdate]);

  useEffect(() => {
    const ws = wavesurferRef.current;
    if (!ws) return;
    if (isPlaying) ws.play();
    else ws.pause();
  }, [isPlaying]);

  useEffect(() => {
    const ws = wavesurferRef.current;
    if (!ws) return;
    const internalTime = ws.getCurrentTime();
    if (Math.abs(internalTime - currentTime) > 0.3) {
      ws.setTime(currentTime);
    }
  }, [currentTime]);

  return <div ref={containerRef} className="w-full" />;
}
