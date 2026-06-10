// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useUser } from "@clerk/nextjs";
import {
  ChevronLeft,
  Command as CommandIcon,
  Film,
  FolderOpen,
  Loader2,
  Music,
  Pause,
  Play,
  RotateCcw,
  Save,
  Settings,
  Smartphone,
  Subtitles,
  Type,
  Wand2,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PresenceCursors } from "./PresenceCursors";
import { ProgressBar } from "./ProgressBar";
import { InspectorPanel } from "./panels/InspectorPanel";
import { MediaPanel } from "./panels/MediaPanel";
import { PreviewPanel } from "./panels/PreviewPanel";
import { TimelinePanel } from "./panels/TimelinePanel";
import { RenderButton } from "./RenderButton";

const PromptPanel = dynamic(() => import("./panels/PromptPanel").then((m) => m.PromptPanel), {
  loading: () => (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col h-[400px] items-center justify-center">
      <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
    </div>
  ),
});

import { toast } from "sonner";
import { type CommandAction, CommandPalette, useCommandPalette } from "@/components/cmdk/CommandPalette";
import { useEditor } from "@/hooks/useEditor";
import { useTimeline } from "@/hooks/useTimeline";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { useAutosave } from "@/lib/hooks/useAutosave";
import type { Asset, CutList, Project } from "@/types/api";
import { SaveStatusBadge } from "./SaveStatusBadge";
import { TemplateLoadDialog } from "./TemplateLoadDialog";
import { TemplateSaveDialog } from "./TemplateSaveDialog";

interface EditorLayoutProps {
  project: Project;
  assets: Asset[];
}

export function EditorLayout({ project, assets }: EditorLayoutProps) {
  const router = useRouter();
  const { user } = useUser();
  const { state, actions } = useEditor({
    cutList: (project.cutList as CutList) || null,
    assets,
  });
  const timeline = useTimeline();
  const [promptOpen, setPromptOpen] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [selectedSubtitleId, setSelectedSubtitleId] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [loadTemplateOpen, setLoadTemplateOpen] = useState(false);
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const api = useApi();

  const aspectRatio = state.cutList?.globals?.aspectRatio || "9:16";
  const setAspectRatio = (ratio: string) => {
    if (!state.cutList) return;
    actions.setCutList({
      ...state.cutList,
      globals: { ...state.cutList.globals, aspectRatio: ratio },
    });
  };
  const undoStackRef = useRef<CutList[]>([]);
  const redoStackRef = useRef<CutList[]>([]);

  useEffect(() => {
    actions.setAssets(assets);
  }, [assets, actions]);

  const handleRollback = useCallback(
    (cl: CutList) => {
      actions.setCutList(cl);
      toast.error("Autosave failed — rolled back to last saved state. Click retry to try again.");
    },
    [actions],
  );

  const { state: saveState, retry: retrySave } = useAutosave({
    projectId: project.id,
    cutList: state.cutList,
    onRollback: handleRollback,
    debounceMs: 1500,
  });

  // Push to undo stack on meaningful changes
  useEffect(() => {
    if (!state.cutList) return;
    const json = JSON.stringify(state.cutList);
    const last = undoStackRef.current[undoStackRef.current.length - 1];
    if (!last || JSON.stringify(last) !== json) {
      undoStackRef.current.push(state.cutList);
      if (undoStackRef.current.length > 50) undoStackRef.current.shift();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.cutList?.globals, state.cutList?.slots.length, state.cutList?.overlays.length]);

  const pushUndo = useCallback((cutList: CutList) => {
    const json = JSON.stringify(cutList);
    const last = undoStackRef.current[undoStackRef.current.length - 1];
    if (!last || JSON.stringify(last) !== json) {
      undoStackRef.current.push(cutList);
      if (undoStackRef.current.length > 50) undoStackRef.current.shift();
    }
  }, []);

  const handleUndo = useCallback(() => {
    if (undoStackRef.current.length > 1) {
      const current = undoStackRef.current.pop();
      const prev = undoStackRef.current[undoStackRef.current.length - 1];
      if (current && prev) {
        redoStackRef.current.push(current);
        actions.setCutList(prev);
      }
    }
  }, [actions]);

  const handlePromptUpdate = useCallback(
    (cutList: CutList) => {
      pushUndo(cutList);
      actions.setCutList(cutList);
    },
    [actions, pushUndo],
  );

  const commandActions = useMemo<CommandAction[]>(
    () => [
      {
        id: "play-pause",
        title: "Play / Pause",
        shortcut: "Space",
        icon: <Play className="h-4 w-4" />,
        section: "Playback",
        perform: () => timeline.togglePlay(),
      },
      {
        id: "seek-start",
        title: "Seek to start",
        shortcut: "Home",
        icon: <RotateCcw className="h-4 w-4" />,
        section: "Playback",
        perform: () => timeline.seek(0),
      },
      {
        id: "ai-prompt",
        title: "Open AI Prompt",
        shortcut: "P",
        icon: <Wand2 className="h-4 w-4" />,
        section: "AI",
        perform: () => setPromptOpen(true),
      },
      {
        id: "render",
        title: "Render video",
        icon: <Film className="h-4 w-4" />,
        section: "Export",
        perform: () => {
          /* render button handles its own state */
        },
      },
      {
        id: "add-text",
        title: "Add text overlay",
        icon: <Type className="h-4 w-4" />,
        section: "Overlays",
        perform: () => toast.info("Select a slot and use the Inspector to add overlays."),
      },
      {
        id: "add-audio",
        title: "Add audio track",
        icon: <Music className="h-4 w-4" />,
        section: "Audio",
        perform: () => toast.info("Drag a song asset onto the timeline."),
      },
      {
        id: "save-template",
        title: "Save as template",
        icon: <Save className="h-4 w-4" />,
        section: "Templates",
        perform: () => state.cutList && setSaveTemplateOpen(true),
      },
      {
        id: "load-template",
        title: "Load template",
        icon: <FolderOpen className="h-4 w-4" />,
        section: "Templates",
        perform: () => setLoadTemplateOpen(true),
      },
      {
        id: "open-settings",
        title: "Open Settings — API Keys",
        icon: <Settings className="h-4 w-4" />,
        section: "Settings",
        perform: () => router.push("/settings/keys"),
      },
    ],
    [timeline, state.cutList, router],
  );

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdkOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if ((e.key === "Delete" || e.key === "Backspace") && state.selectedSlotIndex !== null) {
        e.preventDefault();
        actions.removeSlot(state.selectedSlotIndex, e.shiftKey);
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          // Ctrl+Shift+Z = Redo
          const next = redoStackRef.current.pop();
          if (next) {
            undoStackRef.current.push(next);
            actions.setCutList(next);
          }
        } else {
          handleUndo();
        }
        return;
      }

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
    [timeline, actions, state.selectedSlotIndex, handleUndo],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const selectedSlot =
    state.selectedSlotIndex !== null && state.cutList ? state.cutList.slots[state.selectedSlotIndex] : null;

  return (
    <div className="h-screen bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden relative">
      <PresenceCursors projectId={project.id} userName={user?.firstName || "User"} />
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
            <span>·</span>
            <SaveStatusBadge state={saveState} onRetry={retrySave} />
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
          <button
            onClick={async () => {
              const songAsset = assets.find((a) => a.type === "song");
              const clipAsset = assets.find((a) => a.type === "clip");
              const targetAsset = songAsset || clipAsset;
              if (!targetAsset) {
                toast.error("Upload a song or clip to transcribe");
                return;
              }
              setTranscribing(true);
              try {
                const result = await api.projects.transcribe(project.id, targetAsset.id);
                if (result.subtitles.length > 0 && state.cutList) {
                  actions.setCutList({ ...state.cutList, subtitles: result.subtitles });
                  toast.success(`Generated ${result.subtitles.length} subtitles`);
                } else {
                  toast.info("No speech detected");
                }
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "Transcription failed");
              } finally {
                setTranscribing(false);
              }
            }}
            disabled={transcribing}
            className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition disabled:opacity-50 flex items-center gap-1.5"
            title="Generate subtitles from audio"
          >
            <Subtitles className="w-3.5 h-3.5" />
            {transcribing ? "..." : "Subtitles"}
          </button>

          {/* Aspect ratio dropdown */}
          <div className="relative group">
            <button className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition flex items-center gap-1.5">
              <Smartphone className="w-3.5 h-3.5" />
              {aspectRatio}
            </button>
            <div className="absolute right-0 top-full mt-1 hidden group-hover:flex flex-col bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl overflow-hidden z-50 min-w-[100px]">
              {["9:16", "4:5", "1:1", "16:9"].map((ratio) => (
                <button
                  key={ratio}
                  onClick={() => setAspectRatio(ratio)}
                  className={`px-3 py-2 text-xs text-left hover:bg-zinc-800 transition ${
                    aspectRatio === ratio ? "text-cyan-400 bg-zinc-800/50" : "text-zinc-300"
                  }`}
                >
                  {ratio}
                </button>
              ))}
            </div>
          </div>

          {/* Template save/load */}
          <div className="relative group">
            <button className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition flex items-center gap-1.5">
              <Save className="w-3.5 h-3.5" />
              Template
            </button>
            <div className="absolute right-0 top-full mt-1 hidden group-hover:flex flex-col bg-zinc-900 border border-zinc-800 rounded-lg shadow-xl overflow-hidden z-50 min-w-[140px]">
              <button
                onClick={() => state.cutList && setSaveTemplateOpen(true)}
                className="px-3 py-2 text-xs text-left hover:bg-zinc-800 transition text-zinc-300 flex items-center gap-1.5"
              >
                <Save className="w-3 h-3" /> Save as Template
              </button>
              <button
                onClick={() => setLoadTemplateOpen(true)}
                className="px-3 py-2 text-xs text-left hover:bg-zinc-800 transition text-zinc-300 flex items-center gap-1.5"
              >
                <FolderOpen className="w-3 h-3" /> Load Template
              </button>
            </div>
          </div>

          <RenderButton projectId={project.id} onJobStart={setActiveJobId} />
        </div>
      </div>

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden">
        <MediaPanel projectId={project.id} assets={state.assets} onAssetsChange={actions.setAssets} />

        <div className="flex-1 flex flex-col min-w-0">
          <PreviewPanel
            assets={state.assets}
            currentTime={timeline.currentTime}
            isPlaying={timeline.isPlaying}
            onTimeUpdate={timeline.seek}
            overlays={state.cutList?.overlays || []}
            subtitles={state.cutList?.subtitles}
            showSubtitles={showSubtitles}
            aspectRatio={aspectRatio}
            effects={state.cutList?.globals?.effects}
          />

          <TimelinePanel
            cutList={state.cutList}
            currentTime={timeline.currentTime}
            duration={timeline.duration}
            zoomLevel={timeline.zoomLevel}
            isPlaying={timeline.isPlaying}
            onSeek={timeline.seek}
            onTogglePlay={timeline.togglePlay}
            onZoomIn={timeline.zoomIn}
            onZoomOut={timeline.zoomOut}
            selectedSlotIndex={state.selectedSlotIndex}
            onSelectSlot={actions.selectSlot}
            onUpdateSlot={actions.updateSlot}
            onReorderSlots={actions.reorderSlots}
            selectedSubtitleId={selectedSubtitleId}
            onSelectSubtitle={setSelectedSubtitleId}
          />
        </div>

        <InspectorPanel
          selectedSlot={selectedSlot}
          selectedSlotIndex={state.selectedSlotIndex}
          selectedOverlayId={state.selectedOverlayId}
          overlays={state.cutList?.overlays || []}
          cutList={state.cutList}
          onUpdateSlot={actions.updateSlot}
          onUpdateOverlay={actions.updateOverlay}
          onSelectOverlay={actions.selectOverlay}
          onUpdateEffects={(effects) => {
            if (!state.cutList) return;
            actions.setCutList({
              ...state.cutList,
              globals: { ...state.cutList.globals, effects },
            });
          }}
        />
      </div>

      {promptOpen && (
        <div className="absolute bottom-[220px] right-[300px] w-96 z-50">
          <PromptPanel
            projectId={project.id}
            cutList={state.cutList}
            onUpdateCutlist={handlePromptUpdate}
            onUndo={handleUndo}
            onClose={() => setPromptOpen(false)}
          />
        </div>
      )}

      {state.cutList && (
        <TemplateSaveDialog
          open={saveTemplateOpen}
          onOpenChange={setSaveTemplateOpen}
          cutList={state.cutList}
        />
      )}
      <TemplateLoadDialog
        open={loadTemplateOpen}
        onOpenChange={setLoadTemplateOpen}
        onApply={(cutList) => actions.setCutList(cutList)}
      />

      <CommandPalette open={cmdkOpen} onOpenChange={setCmdkOpen} actions={commandActions} />
      <ProgressBar jobId={activeJobId} />
    </div>
  );
}
