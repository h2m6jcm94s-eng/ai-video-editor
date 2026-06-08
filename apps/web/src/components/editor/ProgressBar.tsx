// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useProgress } from "@/hooks/useProgress";
import { Progress } from "@/components/ui/progress";

interface ProgressBarProps {
  jobId: string | null;
}

export function ProgressBar({ jobId }: ProgressBarProps) {
  const { stage, progress, message, connected } = useProgress(jobId);

  if (!jobId) return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 w-96 bg-zinc-900 border border-zinc-800 rounded-xl p-4 shadow-2xl z-50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium capitalize">{stage || "Initializing..."}</span>
        <span className="text-[10px] text-zinc-500">{connected ? "Connected" : "Reconnecting..."}</span>
      </div>
      <Progress value={progress} className="h-2" />
      <p className="text-[10px] text-zinc-400 mt-2">{message}</p>
    </div>
  );
}
