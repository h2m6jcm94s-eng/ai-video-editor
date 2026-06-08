// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useMemo } from "react";
import { TimelineClip } from "./TimelineClip";
import { Playhead } from "./Playhead";
import type { CutList, Slot, Subtitle } from "@/types/api";

const PIXELS_PER_SECOND = 50;

interface TimelineProps {
  cutList: CutList | null;
  currentTime: number;
  duration: number;
  zoomLevel: number;
  selectedSlotIndex: number | null;
  onSelectSlot: (index: number | null) => void;
  onUpdateSlot: (index: number, slot: Partial<Slot>) => void;
  onReorderSlots: (slots: Slot[]) => void;
  selectedSubtitleId?: string | null;
  onSelectSubtitle?: (id: string | null) => void;
}

export function Timeline({
  cutList,
  currentTime,
  duration,
  zoomLevel,
  selectedSlotIndex,
  onSelectSlot,
  onUpdateSlot,
  selectedSubtitleId,
  onSelectSubtitle,
}: TimelineProps) {
  const slots = cutList?.slots || [];
  const subtitles = cutList?.subtitles || [];
  const totalWidth = Math.max(duration * PIXELS_PER_SECOND * zoomLevel, 800);

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
        {/* Section markers */}
        {(cutList?.globals?.sectionMarkers || []).map((marker) => {
          const left = (marker.startS / duration) * 100;
          const width = ((marker.endS - marker.startS) / duration) * 100;
          return (
            <div
              key={marker.name}
              className="absolute top-0 h-full bg-violet-900/20 border-l border-r border-violet-800/40"
              style={{ left: `${left}%`, width: `${width}%` }}
              title={`${marker.name}: ${formatTime(marker.startS)} - ${formatTime(marker.endS)}`}
            >
              <span className="absolute top-0 left-1 text-[8px] text-violet-400 truncate max-w-full px-0.5">
                {marker.name}
              </span>
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
                    left: `${(o.startTime / duration) * 100}%`,
                    width: `${((o.endTime - o.startTime) / duration) * 100}%`,
                  }}
                >
                  {o.text}
                </div>
              ))}
          </div>
        </div>

        {/* Subtitle track */}
        {subtitles.length > 0 && (
          <div className="h-8 relative mt-1">
            <div className="absolute left-0 top-0 h-full w-8 text-[9px] text-zinc-500 flex items-center pl-1 border-r border-zinc-800 bg-zinc-950/50">
              S1
            </div>
            <div className="ml-8 h-full relative">
              {subtitles.map((sub) => (
                <div
                  key={sub.id}
                  onClick={() => onSelectSubtitle?.(sub.id)}
                  className={`absolute top-1 h-6 rounded px-2 flex items-center text-[9px] truncate cursor-pointer transition-colors ${
                    selectedSubtitleId === sub.id
                      ? "bg-cyan-900/60 border border-cyan-400 text-cyan-200"
                      : "bg-cyan-900/30 border border-cyan-800/50 text-cyan-200 hover:bg-cyan-900/50"
                  }`}
                  style={{
                    left: `${(sub.startS / duration) * 100}%`,
                    width: `${Math.max(((sub.endS - sub.startS) / duration) * 100, 0.5)}%`,
                  }}
                  title={sub.text}
                >
                  {sub.text}
                </div>
              ))}
            </div>
          </div>
        )}
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
