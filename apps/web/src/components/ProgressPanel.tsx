"use client";

import { Loader2, CheckCircle2 } from "lucide-react";

interface Props {
  stage: string;
  progress: number;
  message: string;
}

const STAGE_DISPLAY_MAP: Record<string, string> = {
  initialized: "Initialized",
  probing: "Probing Inputs",
  beat_detection: "Detecting Beats",
  shot_detection: "Detecting Shots",
  style_analysis: "Analyzing Style",
  embedding: "Embedding Clips",
  cutlist_generation: "Generating Cut List",
  ranking: "Ranking Clips",
  awaiting_review: "Awaiting Review",
  rendering: "Rendering Video",
  uploading: "Uploading",
  completed: "Completed",
  queued: "Queued",
};

function getStageStatus(stage: string, progress: number) {
  // Map actual backend stage names to UI steps
  const steps = ["probing", "beat_detection", "shot_detection", "style_analysis", "embedding", "cutlist_generation", "ranking", "rendering", "uploading", "completed"];
  const currentIdx = steps.indexOf(stage);

  return [
    { label: "Shots", status: currentIdx > 2 ? "done" : currentIdx >= 2 ? "active" : "pending" },
    { label: "Beats", status: currentIdx > 1 ? "done" : currentIdx >= 1 ? "active" : "pending" },
    { label: "Style", status: currentIdx > 3 ? "done" : currentIdx >= 3 ? "active" : "pending" },
  ];
}

export function ProgressPanel({ stage, progress, message }: Props) {
  const displayStage = STAGE_DISPLAY_MAP[stage] || stage;
  const stepStatuses = getStageStatus(stage, progress);

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 space-y-4">
      <div className="flex items-center space-x-3">
        {progress >= 100 ? (
          <CheckCircle2 className="w-6 h-6 text-green-500" />
        ) : (
          <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
        )}
        <div>
          <h3 className="font-semibold text-slate-900">
            {progress >= 100 ? "Analysis Complete" : "Analyzing Video..."}
          </h3>
          <p className="text-sm text-slate-500">{message}</p>
        </div>
      </div>

      <div className="relative">
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-xs text-slate-400 capitalize">{displayStage}</span>
          <span className="text-xs text-slate-400">{progress}%</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        {stepStatuses.map((item) => (
          <div
            key={item.label}
            className={`py-2 rounded-lg text-xs font-medium ${
              item.status === "done"
                ? "bg-green-50 text-green-700"
                : item.status === "active"
                ? "bg-indigo-50 text-indigo-700"
                : "bg-slate-50 text-slate-400"
            }`}
          >
            {item.label}
          </div>
        ))}
      </div>
    </div>
  );
}
