// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

interface PlayheadProps {
  currentTime: number;
  duration: number;
}

export function Playhead({ currentTime, duration }: PlayheadProps) {
  const position = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div
      className="absolute top-0 bottom-0 w-px bg-red-500 z-30 pointer-events-none"
      style={{ left: `${position}%` }}
    >
      <div className="absolute -top-0 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[4px] border-r-[4px] border-t-[6px] border-l-transparent border-r-transparent border-t-red-500" />
    </div>
  );
}
