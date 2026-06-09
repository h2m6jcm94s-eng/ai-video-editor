// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState, useRef, useCallback } from "react";
import type { Slot } from "@/types/api";

interface TimelineClipProps {
  slot: Slot;
  index: number;
  duration: number;
  isSelected: boolean;
  onSelect: () => void;
  onUpdate: (slot: Partial<Slot>) => void;
}

export function TimelineClip({ slot, index, duration, isSelected, onSelect, onUpdate }: TimelineClipProps) {
  const [isDragging, setIsDragging] = useState(false);
  const startXRef = useRef(0);
  const startValueRef = useRef(0);
  const containerWidthRef = useRef(0);
  const slotRef = useRef(slot);
  const durationRef = useRef(duration);

  // Keep refs in sync to avoid stale closures
  slotRef.current = slot;
  durationRef.current = duration;

  const left = (slot.startS / duration) * 100;
  const width = (slot.durationS / duration) * 100;

  const handleMouseDown = useCallback((e: React.MouseEvent, mode: "move" | "resize-left" | "resize-right") => {
    e.stopPropagation();
    setIsDragging(true);
    startXRef.current = e.clientX;
    startValueRef.current =
      mode === "move" ? slotRef.current.startS : mode === "resize-left" ? slotRef.current.startS : slotRef.current.durationS;
    containerWidthRef.current = (e.currentTarget.parentElement?.offsetWidth || 1);

    const handleMouseMove = (ev: MouseEvent) => {
      const deltaPx = ev.clientX - startXRef.current;
      const cw = containerWidthRef.current;
      const dur = durationRef.current;
      const deltaSec = (deltaPx / cw) * dur;

      if (mode === "move") {
        const newStart = Math.max(0, startValueRef.current + deltaSec);
        onUpdate({ startS: newStart });
      } else if (mode === "resize-left") {
        const newStart = Math.max(0, startValueRef.current + deltaSec);
        const newDuration = slotRef.current.durationS + (slotRef.current.startS - newStart);
        if (newDuration > 0.1) onUpdate({ startS: newStart, durationS: newDuration });
      } else if (mode === "resize-right") {
        const newDuration = Math.max(0.1, startValueRef.current + deltaSec);
        onUpdate({ durationS: newDuration });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  }, [onUpdate]);

  return (
    <div
      className={`absolute top-1 h-8 rounded border flex items-center px-1 cursor-pointer select-none text-[9px] font-medium transition ${
        isSelected
          ? "bg-indigo-900/60 border-indigo-500 text-indigo-200"
          : "bg-zinc-800 border-zinc-700 text-zinc-300 hover:bg-zinc-700"
      } ${isDragging ? "opacity-80" : ""}`}
      style={{ left: `${left}%`, width: `${Math.max(width, 0.5)}%` }}
      onClick={(e) => {
        if (!isDragging) onSelect();
      }}
      role="button"
      aria-label={`Clip ${index}: ${slot.targetShotType}`}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect();
      }}
    >
      {/* Resize left handle */}
      <div
        className="absolute left-0 top-0 bottom-0 w-2 cursor-w-resize hover:bg-white/10 rounded-l"
        onMouseDown={(e) => handleMouseDown(e, "resize-left")}
      />
      <span className="truncate px-1 z-10 pointer-events-none">
        {slot.targetShotType}
      </span>
      {/* Resize right handle */}
      <div
        className="absolute right-0 top-0 bottom-0 w-2 cursor-e-resize hover:bg-white/10 rounded-r"
        onMouseDown={(e) => handleMouseDown(e, "resize-right")}
      />
    </div>
  );
}
