// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useRef } from "react";
import { Play, Pause, SkipBack, SkipForward, ZoomIn, ZoomOut } from "lucide-react";
import { Timeline } from "../timeline/Timeline";
import type { CutList, Slot } from "@/types/api";

interface TimelinePanelProps {
  cutList: CutList | null;
  currentTime: number;
  duration: number;
  zoomLevel: number;
  isPlaying: boolean;
  onSeek: (time: number) => void;
  onTogglePlay: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  selectedSlotIndex: number | null;
  onSelectSlot: (index: number | null) => void;
  onUpdateSlot: (index: number, slot: Partial<Slot>) => void;
  onReorderSlots: (slots: Slot[]) => void;
  selectedSubtitleId?: string | null;
  onSelectSubtitle?: (id: string | null) => void;
}

export function TimelinePanel({
  cutList,
  currentTime,
  duration,
  zoomLevel,
  isPlaying,
  onSeek,
  onTogglePlay,
  onZoomIn,
  onZoomOut,
  selectedSlotIndex,
  onSelectSlot,
  onUpdateSlot,
  onReorderSlots,
  selectedSubtitleId,
  onSelectSubtitle,
}: TimelinePanelProps) {
  const trackRef = useRef<HTMLDivElement>(null);

  const handleTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const ratio = x / rect.width;
    onSeek(ratio * duration);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const assetId = e.dataTransfer.getData("assetId");
    if (!assetId || !cutList) return;
    // Insert at drop position
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const ratio = x / rect.width;
    const startTime = ratio * duration;
    const newSlot: Slot = {
      index: cutList.slots.length,
      startS: startTime,
      duration_s: 2,
      beatIndex: 0,
      section: "custom",
      transitionIn: "hard_cut",
      transitionOut: "hard_cut",
      targetShotType: "medium",
      subjectHint: "",
      motionHint: "static",
      energyLevel: 0.5,
      requiredTags: [],
      avoidTags: [],
      selectedClipId: assetId,
      rankedClipIds: null,
      confidence: null,
    };
    onReorderSlots([...cutList.slots, newSlot]);
  };

  return (
    <div className="h-[200px] border-t border-zinc-800 bg-zinc-950 flex flex-col shrink-0">
      {/* Timeline Toolbar */}
      <div className="h-8 border-b border-zinc-800 flex items-center px-3 gap-2">
        <button onClick={onTogglePlay} className="p-1 hover:bg-zinc-800 rounded" aria-label={isPlaying ? "Pause" : "Play"}>
          {isPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
        </button>
        <button onClick={() => onSeek(0)} className="p-1 hover:bg-zinc-800 rounded" aria-label="Skip to start">
          <SkipBack className="w-3 h-3" />
        </button>
        <button onClick={() => onSeek(duration)} className="p-1 hover:bg-zinc-800 rounded" aria-label="Skip to end">
          <SkipForward className="w-3 h-3" />
        </button>
        <div className="w-px h-4 bg-zinc-800 mx-1" />
        <span className="text-[10px] font-mono text-zinc-400 w-16 text-center">
          {formatTime(currentTime)}
        </span>
        <span className="text-[10px] text-zinc-600">/</span>
        <span className="text-[10px] font-mono text-zinc-500 w-16 text-center">
          {formatTime(duration)}
        </span>
        <div className="flex-1" />
        <button onClick={onZoomIn} className="p-1 hover:bg-zinc-800 rounded" aria-label="Zoom in">
          <ZoomIn className="w-3 h-3" />
        </button>
        <button onClick={onZoomOut} className="p-1 hover:bg-zinc-800 rounded" aria-label="Zoom out">
          <ZoomOut className="w-3 h-3" />
        </button>
      </div>

      {/* Timeline Tracks */}
      <div
        className="flex-1 overflow-x-auto overflow-y-hidden relative"
        onClick={handleTrackClick}
        ref={trackRef}
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        <Timeline
          cutList={cutList}
          currentTime={currentTime}
          duration={duration}
          zoomLevel={zoomLevel}
          selectedSlotIndex={selectedSlotIndex}
          onSelectSlot={onSelectSlot}
          onUpdateSlot={onUpdateSlot}
          onReorderSlots={onReorderSlots}
          selectedSubtitleId={selectedSubtitleId}
          onSelectSubtitle={onSelectSubtitle}
        />
      </div>
    </div>
  );
}

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const ms = Math.floor((sec % 1) * 100);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}:${ms.toString().padStart(2, "0")}`;
}
