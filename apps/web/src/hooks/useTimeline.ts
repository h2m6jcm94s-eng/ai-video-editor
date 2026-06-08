// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState, useCallback, useRef, useEffect } from "react";

interface TimelineState {
  currentTime: number;
  duration: number;
  isPlaying: boolean;
  zoomLevel: number;
}

export function useTimeline(initialDuration = 30) {
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(initialDuration);
  const [isPlaying, setIsPlaying] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const rafRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(0);

  const play = useCallback(() => {
    setIsPlaying(true);
    lastTimeRef.current = performance.now();
  }, []);

  const pause = useCallback(() => {
    setIsPlaying(false);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
  }, []);

  const togglePlay = useCallback(() => {
    setIsPlaying((prev) => !prev);
  }, []);

  const seek = useCallback((time: number) => {
    const dur = duration || 1; // guard against 0
    setCurrentTime(Math.max(0, Math.min(time, dur)));
  }, [duration]);

  const zoomIn = useCallback(() => setZoomLevel((z) => Math.min(z * 1.2, 10)), []);
  const zoomOut = useCallback(() => setZoomLevel((z) => Math.max(z / 1.2, 0.1)), []);

  useEffect(() => {
    if (!isPlaying) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const tick = (now: number) => {
      const delta = (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;
      setCurrentTime((prev) => {
        const next = prev + delta;
        const dur = duration || 1;
        if (next >= dur) {
          setIsPlaying(false);
          return dur;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(tick);
    };

    lastTimeRef.current = performance.now();
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, duration]);

  return {
    currentTime,
    duration,
    isPlaying,
    zoomLevel,
    play,
    pause,
    togglePlay,
    seek,
    setDuration,
    zoomIn,
    zoomOut,
  };
}
