// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect, useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, Play, Pause, Maximize2, RotateCcw } from "lucide-react";
import { MediaPanel } from "./panels/MediaPanel";
import { PreviewPanel } from "./panels/PreviewPanel";
import { InspectorPanel } from "./panels/InspectorPanel";
import { TimelinePanel } from "./panels/TimelinePanel";
import { PromptPanel } from "./panels/PromptPanel";
import { RenderButton } from "./RenderButton";
import { useEditor } from "@/hooks/useEditor";
import { useTimeline } from "@/hooks/useTimeline";
import type { Project, Asset, CutList } from "@/types/api";

interface EditorLayoutProps {
  project: Project;
  assets: Asset[];
}

export function EditorLayout({ project, assets }: EditorLayoutProps) {
  const router = useRouter();
  const { state, actions } = useEditor({
    cutList: (project.cutList as CutList) || null,
    assets,
  });
  const timeline = useTimeline();
  const [promptOpen, setPromptOpen] = useState(false);

  useEffect(() => {
    actions.setAssets(assets);
  }, [assets, actions]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case " ":
          e.preventDefault();
          timeline.togglePlay();
          break;
        case "j":
          timeline.seek(timeline.currentTime - 5);
          break;
        case "l":
          timeline.seek(timeline.currentTime + 5);
          break;
        case "ArrowLeft":
          timeline.seek(timeline.currentTime - 1);
          break;
        case "ArrowRight":
          timeline.seek(timeline.currentTime + 1);
          break;
      }
    },
    [timeline]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const selectedSlot =
    state.selectedSlotIndex !== null && state.cutList
      ? state.cutList.slots[state.selectedSlotIndex]
      : null;

  return (
    <div className="h-screen bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden">
      {/* Top Bar */}
      <div className="h-14 border-b border-zinc-800 flex items-center px-4 gap-4 shrink-0 bg-zinc-950/80 backdrop-blur-sm">
        <button
          onClick={() => router.push("/dashboard")}
          className="p-2 hover:bg-zinc-800 rounded-lg transition"
          aria-label="Back to dashboard"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-medium truncate">{project.name}</h1>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="capitalize">{project.styleTier.replace("_", " ")}</span>
            <span>·</span>
            <span className="capitalize">{project.mode}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={timeline.togglePlay}
            className="p-2 hover:bg-zinc-800 rounded-lg transition"
            aria-label={timeline.isPlaying ? "Pause" : "Play"}
          >
            {timeline.isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
          </button>
          <button
            onClick={() => timeline.seek(0)}
            className="p-2 hover:bg-zinc-800 rounded-lg transition"
            aria-label="Reset to start"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setPromptOpen((p) => !p)}
            className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition"
          >
            AI Prompt
          </button>
          <RenderButton projectId={project.id} />
        </div>
      </div>

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden">
        <MediaPanel
          projectId={project.id}
          assets={state.assets}
          onAssetsChange={actions.setAssets}
        />

        <div className="flex-1 flex flex-col min-w-0">
          <PreviewPanel
            assets={state.assets}
            currentTime={timeline.currentTime}
            isPlaying={timeline.isPlaying}
            onTimeUpdate={timeline.seek}
            overlays={state.cutList?.overlays || []}
          />

          <TimelinePanel
            cutList={state.cutList}
            currentTime={timeline.currentTime}
            duration={timeline.duration}
            zoomLevel={timeline.zoomLevel}
            isPlaying={timeline.isPlaying}
            onSeek={timeline.seek}
            onTogglePlay={timeline.togglePlay}
            selectedSlotIndex={state.selectedSlotIndex}
            onSelectSlot={actions.selectSlot}
            onUpdateSlot={actions.updateSlot}
            onReorderSlots={actions.reorderSlots}
          />
        </div>

        <InspectorPanel
          selectedSlot={selectedSlot}
          selectedOverlayId={state.selectedOverlayId}
          overlays={state.cutList?.overlays || []}
          onUpdateSlot={actions.updateSlot}
          onUpdateOverlay={actions.updateOverlay}
          onSelectOverlay={actions.selectOverlay}
        />
      </div>

      {promptOpen && (
        <div className="absolute bottom-[220px] right-[300px] w-96 z-50">
          <PromptPanel
            projectId={project.id}
            cutList={state.cutList}
            onUpdateCutlist={actions.setCutList}
            onClose={() => setPromptOpen(false)}
          />
        </div>
      )}
    </div>
  );
}
