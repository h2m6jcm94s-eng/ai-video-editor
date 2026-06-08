// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useMemo } from "react";
import { TimelineClip } from "./TimelineClip";
import { Playhead } from "./Playhead";
import type { CutList, Slot } from "@/types/api";

interface TimelineProps {
  cutList: CutList | null;
  currentTime: number;
  duration: number;
  zoomLevel: number;
  selectedSlotIndex: number | null;
  onSelectSlot: (index: number | null) => void;
  onUpdateSlot: (index: number, slot: Partial<Slot>) => void;
  onReorderSlots: (slots: Slot[]) => void;
}

export function Timeline({
  cutList,
  currentTime,
  duration,
  zoomLevel,
  selectedSlotIndex,
  onSelectSlot,
  onUpdateSlot,
}: TimelineProps) {
  const slots = cutList?.slots || [];
  const totalWidth = Math.max(duration * 50 * zoomLevel, 800);

  const timeMarkers = useMemo(() => {
    const markers = [];
    const step = duration > 60 ? 10 : duration > 30 ? 5 : 1;
    for (let t = 0; t <= duration; t += step) {
      markers.push(t);
    }
    return markers;
  }, [duration]);

  return (
    <div className="relative h-full" style={{ width: totalWidth }}>
      {/* Time ruler */}
      <div className="h-6 border-b border-zinc-800 relative">
        {timeMarkers.map((t) => {
          const left = (t / duration) * 100;
          return (
            <div
              key={t}
              className="absolute top-0 h-full flex flex-col items-center"
              style={{ left: `${left}%`, transform: "translateX(-50%)" }}
            >
              <span className="text-[9px] text-zinc-500 mt-0.5">{formatTime(t)}</span>
            </div>
          );
        })}
      </div>

      {/* Tracks */}
      <div className="relative pt-2">
        {/* Video track */}
        <div className="h-10 relative">
          <div className="absolute left-0 top-0 h-full w-8 text-[9px] text-zinc-500 flex items-center pl-1 border-r border-zinc-800 bg-zinc-950/50">
            V1
          </div>
          <div className="ml-8 h-full relative">
            {slots.map((slot, index) => (
              <TimelineClip
                key={`${slot.index}-${index}`}
                slot={slot}
                index={index}
                duration={duration}
                isSelected={selectedSlotIndex === index}
                onSelect={() => onSelectSlot(index)}
                onUpdate={(s) => onUpdateSlot(index, s)}
              />
            ))}
          </div>
        </div>

        {/* Audio track */}
        <div className="h-8 relative mt-1">
          <div className="absolute left-0 top-0 h-full w-8 text-[9px] text-zinc-500 flex items-center pl-1 border-r border-zinc-800 bg-zinc-950/50">
            A1
          </div>
          <div className="ml-8 h-full relative">
            <div
              className="absolute top-1 h-6 rounded bg-emerald-900/40 border border-emerald-800/50"
              style={{ left: "0%", width: "100%" }}
            />
          </div>
        </div>

        {/* Text track */}
        <div className="h-8 relative mt-1">
          <div className="absolute left-0 top-0 h-full w-8 text-[9px] text-zinc-500 flex items-center pl-1 border-r border-zinc-800 bg-zinc-950/50">
            T1
          </div>
          <div className="ml-8 h-full relative">
            {(cutList?.overlays || [])
              .filter((o) => o.type === "text")
              .map((o) => (
                <div
                  key={o.id}
                  className="absolute top-1 h-6 rounded bg-amber-900/40 border border-amber-800/50 px-2 flex items-center text-[9px] text-amber-200 truncate"
                  style={{
                    left: `${(o.start_time / duration) * 100}%`,
                    width: `${((o.end_time - o.start_time) / duration) * 100}%`,
                  }}
                >
                  {o.text}
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Playhead */}
      <Playhead currentTime={currentTime} duration={duration} />
    </div>
  );
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
