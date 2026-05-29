// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useState } from "react";
import { UploadZone } from "@/components/UploadZone";
import { StyleTierSelector } from "@/components/StyleTierSelector";
import { ProgressPanel } from "@/components/ProgressPanel";
import { TimelinePreview } from "@/components/TimelinePreview";
import { VideoPlayer } from "@/components/VideoPlayer";
import type { StyleTier, EditMode, Project } from "@ai-video-editor/shared-types";

export default function Home() {
  const [project, setProject] = useState<Project | null>(null);
  const [styleTier, setStyleTier] = useState<StyleTier>("full_style");
  const [editMode, setEditMode] = useState<EditMode>("auto");
  const [analysisProgress, setAnalysisProgress] = useState({
    stage: "",
    progress: 0,
    message: "",
  });
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [renderResult, setRenderResult] = useState<string | null>(null);

  const handleCreateProject = async (name: string) => {
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, styleTier, mode: editMode }),
    });
    const data = await res.json();
    setProject(data.project);
  };

  const handleStartAnalysis = async () => {
    if (!project) return;
    setIsAnalyzing(true);

    // Simulate analysis progress
    const stages = [
      { stage: "probe", message: "Probing video metadata..." },
      { stage: "shots", message: "Detecting shot boundaries..." },
      { stage: "beats", message: "Extracting beat grid..." },
      { stage: "style", message: "Analyzing color grade & style..." },
      { stage: "text", message: "Parsing text overlays..." },
      { stage: "cutlist", message: "Generating cut list..." },
    ];

    for (let i = 0; i < stages.length; i++) {
      setAnalysisProgress({
        stage: stages[i].stage,
        progress: Math.round(((i + 1) / stages.length) * 100),
        message: stages[i].message,
      });
      await new Promise((r) => setTimeout(r, 800));
    }

    setIsAnalyzing(false);
  };

  const handleRender = async () => {
    if (!project) return;
    const res = await fetch("/api/renders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: project.id }),
    });
    const data = await res.json();
    // Poll for result
    setRenderResult("/sample-output.mp4");
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      <header className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <h1 className="text-xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
            AI Video Editor
          </h1>
          <div className="text-sm text-slate-500">Reference Style Matching</div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {!project ? (
          <div className="max-w-2xl mx-auto space-y-8">
            <div className="text-center space-y-4">
              <h2 className="text-4xl font-bold text-slate-900">
                Match Any Video Style
              </h2>
              <p className="text-lg text-slate-600">
                Upload a reference video, your clips, and a song. Our AI parses
                the reference's editing style and applies it to your footage.
              </p>
            </div>

            <div className="bg-white rounded-2xl shadow-xl p-8 space-y-6">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Project Name
                </label>
                <input
                  type="text"
                  placeholder="My Awesome Edit"
                  className="w-full px-4 py-3 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      handleCreateProject((e.target as HTMLInputElement).value);
                    }
                  }}
                />
              </div>

              <StyleTierSelector
                value={styleTier}
                onChange={setStyleTier}
                mode={editMode}
                onModeChange={setEditMode}
              />

              <button
                onClick={() => {
                  const input = document.querySelector('input[type="text"]') as HTMLInputElement;
                  if (input.value) handleCreateProject(input.value);
                }}
                className="w-full py-3 px-6 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg transition"
              >
                Create Project
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-1 space-y-6">
              <div className="bg-white rounded-xl shadow-lg p-6 space-y-4">
                <h3 className="font-semibold text-slate-900">Upload Assets</h3>
                <UploadZone
                  projectId={project.id}
                  type="reference_video"
                  label="Reference Video"
                  accept="video/*"
                />
                <UploadZone
                  projectId={project.id}
                  type="user_clip"
                  label="Your Clips"
                  accept="video/*"
                  multiple
                />
                <UploadZone
                  projectId={project.id}
                  type="song"
                  label="Your Song"
                  accept="audio/*"
                />
              </div>

              <div className="bg-white rounded-xl shadow-lg p-6">
                <h3 className="font-semibold text-slate-900 mb-4">Settings</h3>
                <StyleTierSelector
                  value={styleTier}
                  onChange={setStyleTier}
                  mode={editMode}
                  onModeChange={setEditMode}
                />
              </div>

              {!isAnalyzing && !renderResult && (
                <button
                  onClick={handleStartAnalysis}
                  className="w-full py-3 px-6 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg transition"
                >
                  Analyze & Generate Edit
                </button>
              )}

              {renderResult && (
                <button
                  onClick={handleRender}
                  className="w-full py-3 px-6 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-lg transition"
                >
                  Render Final Video
                </button>
              )}
            </div>

            <div className="lg:col-span-2 space-y-6">
              {isAnalyzing && (
                <ProgressPanel
                  stage={analysisProgress.stage}
                  progress={analysisProgress.progress}
                  message={analysisProgress.message}
                />
              )}

              {!isAnalyzing && !renderResult && project && (
                <TimelinePreview project={project} />
              )}

              {renderResult && (
                <div className="bg-white rounded-xl shadow-lg p-6">
                  <h3 className="font-semibold text-slate-900 mb-4">Result</h3>
                  <VideoPlayer src={renderResult} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
