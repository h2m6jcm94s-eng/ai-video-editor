// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useUser } from "@clerk/nextjs";
import {
  ChevronLeft,
  Command as CommandIcon,
  Film,
  FolderOpen,
  Library,
  Loader2,
  MessageSquare,
  Music,
  PanelLeft,
  PanelRight,
  Pause,
  Play,
  RotateCcw,
  Save,
  ScanLine,
  Settings,
  SlidersHorizontal,
  Smartphone,
  Subtitles,
  Type,
  Wand2,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PresenceCursors } from "./PresenceCursors";
import { ProgressBar } from "./ProgressBar";
import { InspectorPanel } from "./panels/InspectorPanel";
import { MediaPanel } from "./panels/MediaPanel";
import { PreviewPanel } from "./panels/PreviewPanel";
import { TimelinePanel } from "./panels/TimelinePanel";
import { RenderButton } from "./RenderButton";
import { RenderDownload } from "./RenderDownload";
import { SegmentPanel } from "./SegmentPanel";

const PromptPanel = dynamic(() => import("./panels/PromptPanel").then((m) => m.PromptPanel), {
  loading: () => (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col h-[400px] items-center justify-center">
      <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
    </div>
  ),
});

import { toast } from "sonner";
import { type CommandAction, CommandPalette, useCommandPalette } from "@/components/cmdk/CommandPalette";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAssetPoller } from "@/hooks/useAssetPoller";
import { useEditor } from "@/hooks/useEditor";
import { useProgress } from "@/hooks/useProgress";
import { useRenderStatus } from "@/hooks/useRenderStatus";
import { useStyleAnalysis } from "@/hooks/useStyleAnalysis";
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
  const renderStatus = useRenderStatus(project.id);
  useAssetPoller(project.id, state.assets, actions.setAssets);
  const [promptOpen, setPromptOpen] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [showSubtitles, setShowSubtitles] = useState(true);
  const [selectedSubtitleId, setSelectedSubtitleId] = useState<string | null>(null);
  const [transcribing, setTranscribing] = useState(false);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [loadTemplateOpen, setLoadTemplateOpen] = useState(false);
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const [generatingRef, setGeneratingRef] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<null | "media" | "inspector" | "segment">(null);
  const isMobile = useIsMobile();
  const styleAnalysis = useStyleAnalysis(project.id);
  const api = useApi();

  useProgress(activeJobId, {
    onComplete: async () => {
      try {
        const { job } = await api.projects.getGeneration(project.id);
        if (job.outputCutList) {
          actions.promptApply(job.outputCutList as CutList);
          toast.success("Cut-list ready — generated from reference");
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Generation result unavailable");
      } finally {
        setActiveJobId(null);
      }
    },
    onFailed: (message) => {
      toast.error(message);
      setActiveJobId(null);
    },
    fallbackPoll: async () => {
      try {
        const { job } = await api.projects.getGeneration(project.id);
        return {
          type: job.status,
          stage: job.stage,
          progress: job.progress,
          message: job.status === "complete" ? "Generation complete" : job.errorMessage || "Generating...",
        };
      } catch {
        return null;
      }
    },
  });

  const aspectRatio = state.cutList?.globals?.aspectRatio || "9:16";
  const setAspectRatio = (ratio: string) => {
    if (!state.cutList) return;
    actions.setCutList({
      ...state.cutList,
      globals: { ...state.cutList.globals, aspectRatio: ratio },
    });
  };
  useEffect(() => {
    actions.setAssets(assets);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assets]);

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
          actions.redo();
        } else {
          actions.undo();
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
    [timeline, actions, state.selectedSlotIndex],
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
      <div
        data-testid="editor-topbar"
        className="h-14 border-b border-zinc-800 flex items-center px-4 gap-4 shrink-0 bg-zinc-950/80 backdrop-blur-sm"
      >
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
        <div className="flex items-center gap-1 sm:gap-2 overflow-x-auto [&::-webkit-scrollbar]:hidden max-w-[55vw] sm:max-w-none">
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
            className="px-2 sm:px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition whitespace-nowrap"
          >
            <span className="hidden sm:inline">AI Prompt</span>
            <Wand2 className="w-4 h-4 sm:hidden" />
          </button>
          <button
            onClick={async () => {
              const refAsset = state.assets.find((a) => a.type === "reference_video");
              if (!refAsset) {
                toast.error("Upload a reference video first");
                return;
              }
              setGeneratingRef(true);
              try {
                let analysis = styleAnalysis.analysis;
                if (!analysis) {
                  analysis = await styleAnalysis.refresh();
                }
                if (!analysis) {
                  toast.info("Style analysis is still running. Try again in a few seconds.");
                  return;
                }
                const { job } = await api.projects.generate(project.id, {
                  prompt: `Generate a cutlist that matches the reference video's editing style, shot types, transitions, and pacing. Analyze the reference and replicate its visual rhythm.`,
                });
                setActiveJobId(job.id);
                toast.info("Generation started — you can keep editing while it runs.");
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "Reference generation failed");
              } finally {
                setGeneratingRef(false);
              }
            }}
            disabled={
              generatingRef ||
              !state.assets.some((a) => a.type === "reference_video") ||
              styleAnalysis.isPending ||
              !!activeJobId
            }
            className="px-2 sm:px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition disabled:opacity-50 whitespace-nowrap"
            data-testid="generate-from-reference"
          >
            <span className="hidden sm:inline">
              {generatingRef
                ? "Generating..."
                : styleAnalysis.isPending
                  ? "Analyzing reference..."
                  : activeJobId
                    ? "Generation running..."
                    : "Generate from reference"}
            </span>
            <Wand2 className="w-4 h-4 sm:hidden" />
          </button>
          <button
            onClick={async () => {
              const songAsset = state.assets.find((a) => a.type === "song");
              const clipAsset = state.assets.find((a) => a.type === "clip");
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
            className="px-2 sm:px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap"
            title="Generate subtitles from audio"
          >
            <Subtitles className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">{transcribing ? "..." : "Subtitles"}</span>
          </button>

          {/* Aspect ratio dropdown */}
          <div className="relative group">
            <button className="px-2 sm:px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition flex items-center gap-1.5 whitespace-nowrap">
              <Smartphone className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{aspectRatio}</span>
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
            <button className="px-2 sm:px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded-lg transition flex items-center gap-1.5 whitespace-nowrap">
              <Save className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Template</span>
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

          <RenderButton projectId={project.id} assets={state.assets} onJobStart={setActiveJobId} />
          {renderStatus.latestRender && !renderStatus.activeRender && (
            <>
              <span
                className={`text-xs px-2 py-1 rounded-lg ${
                  renderStatus.latestRender.status === "complete"
                    ? "bg-green-900/50 text-green-400"
                    : "bg-red-900/50 text-red-400"
                }`}
                data-render-status={renderStatus.latestRender.status}
                data-testid="render-status"
              >
                {renderStatus.latestRender.status === "complete" ? "Render complete" : "Render failed"}
              </span>
              <RenderDownload render={renderStatus.latestRender} />
            </>
          )}
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
        <SegmentPanel projectId={project.id} assets={state.assets} />
      </div>

      {/* Mobile bottom toolbar */}
      <div className="md:hidden h-14 border-t border-zinc-800 bg-zinc-950 shrink-0 flex items-center justify-around px-2">
        <button
          onClick={() => setMobilePanel("media")}
          className="flex flex-col items-center gap-0.5 p-2 text-zinc-400 hover:text-zinc-100"
          aria-label="Media"
        >
          <Library className="w-5 h-5" />
          <span className="text-[10px]">Media</span>
        </button>
        <button
          onClick={() => setMobilePanel("inspector")}
          className="flex flex-col items-center gap-0.5 p-2 text-zinc-400 hover:text-zinc-100"
          aria-label="Inspector"
        >
          <SlidersHorizontal className="w-5 h-5" />
          <span className="text-[10px]">Edit</span>
        </button>
        <button
          onClick={() => setPromptOpen(true)}
          className="flex flex-col items-center gap-0.5 p-2 text-cyan-400 hover:text-cyan-300"
          aria-label="AI Prompt"
        >
          <MessageSquare className="w-5 h-5" />
          <span className="text-[10px]">AI</span>
        </button>
        <button
          onClick={() => setMobilePanel("segment")}
          className="flex flex-col items-center gap-0.5 p-2 text-zinc-400 hover:text-zinc-100"
          aria-label="Segment"
        >
          <ScanLine className="w-5 h-5" />
          <span className="text-[10px]">Mask</span>
        </button>
      </div>

      {/* Mobile panel sheets */}
      {mobilePanel !== null && (
        <>
          <Sheet open={mobilePanel === "media"} onOpenChange={(open) => !open && setMobilePanel(null)}>
            <SheetContent
              side="left"
              className="bg-zinc-950 border-zinc-800 text-zinc-100 w-3/4 sm:max-w-sm p-0"
            >
              <SheetHeader className="p-4 border-b border-zinc-800">
                <SheetTitle className="text-sm text-zinc-100">Media</SheetTitle>
              </SheetHeader>
              <div className="flex-1 overflow-auto">
                <MediaPanel projectId={project.id} assets={state.assets} onAssetsChange={actions.setAssets} />
              </div>
            </SheetContent>
          </Sheet>

          <Sheet open={mobilePanel === "inspector"} onOpenChange={(open) => !open && setMobilePanel(null)}>
            <SheetContent
              side="right"
              className="bg-zinc-950 border-zinc-800 text-zinc-100 w-3/4 sm:max-w-sm p-0"
            >
              <SheetHeader className="p-4 border-b border-zinc-800">
                <SheetTitle className="text-sm text-zinc-100">Inspector</SheetTitle>
              </SheetHeader>
              <div className="flex-1 overflow-auto">
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
            </SheetContent>
          </Sheet>

          <Sheet open={mobilePanel === "segment"} onOpenChange={(open) => !open && setMobilePanel(null)}>
            <SheetContent
              side="right"
              className="bg-zinc-950 border-zinc-800 text-zinc-100 w-3/4 sm:max-w-sm p-0"
            >
              <SheetHeader className="p-4 border-b border-zinc-800">
                <SheetTitle className="text-sm text-zinc-100">Segment</SheetTitle>
              </SheetHeader>
              <div className="flex-1 overflow-auto">
                <SegmentPanel projectId={project.id} assets={state.assets} />
              </div>
            </SheetContent>
          </Sheet>
        </>
      )}

      {/* Prompt panel: bottom sheet on mobile, floating card on desktop */}
      {isMobile ? (
        <Sheet open={promptOpen} onOpenChange={setPromptOpen}>
          <SheetContent side="bottom" className="bg-zinc-950 border-zinc-800 text-zinc-100 h-[60vh]">
            <PromptPanel
              projectId={project.id}
              cutList={state.cutList}
              onPromptApply={actions.promptApply}
              onUndo={actions.undo}
              onClose={() => setPromptOpen(false)}
            />
          </SheetContent>
        </Sheet>
      ) : (
        promptOpen && (
          <div className="absolute bottom-[220px] right-[300px] w-96 z-50">
            <PromptPanel
              projectId={project.id}
              cutList={state.cutList}
              onPromptApply={actions.promptApply}
              onUndo={actions.undo}
              onClose={() => setPromptOpen(false)}
            />
          </div>
        )
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
