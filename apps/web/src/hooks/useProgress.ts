// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useCallback, useState } from "react";
import { useApi } from "@/lib/api/client";
import { useSSE } from "./useSSE";

interface ProgressState {
  stage: string;
  progress: number;
  message: string;
  connected: boolean;
}

interface ProgressEvent {
  type?: string;
  stage?: string;
  progress?: number;
  message?: string;
}

interface UseProgressOptions {
  onComplete?: () => void;
  onFailed?: (message: string) => void;
  fallbackPoll?: () => Promise<ProgressEvent | null>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

export function useProgress(jobId: string | null, options: UseProgressOptions = {}) {
  const api = useApi();
  const { onComplete, onFailed, fallbackPoll: customFallbackPoll } = options;
  const [state, setState] = useState<ProgressState>({
    stage: "",
    progress: 0,
    message: "",
    connected: false,
  });

  const handleEvent = useCallback(
    (data: ProgressEvent) => {
      if (data.type === "connected") return;
      setState({
        stage: data.stage || "",
        progress: data.progress || 0,
        message: data.message || "",
        connected: true,
      });
      if (data.type === "complete") {
        onComplete?.();
      } else if (data.type === "failed") {
        onFailed?.(data.message || "Job failed");
      }
    },
    [onComplete, onFailed],
  );

  const defaultFallbackPoll = useCallback(async () => {
    if (!jobId) return null;
    try {
      const { job } = await api.renders.get(jobId);
      if (!job) return null;
      const ev: ProgressEvent = {
        type: job.status,
        stage: job.stage,
        progress: job.progress,
        message: job.status === "complete" ? "Render complete" : job.errorMessage || "",
      };
      return ev;
    } catch {
      return null;
    }
  }, [jobId, api]);

  const fallbackPoll = customFallbackPoll || defaultFallbackPoll;

  const { connected } = useSSE<ProgressEvent>({
    url: jobId ? `${API_BASE}/progress/${jobId}/events` : "",
    enabled: !!jobId,
    onEvent: handleEvent,
    maxReconnectAttempts: 5,
    fallbackPoll,
    pollIntervalMs: 3000,
    shouldClose: (data) => data.type === "complete" || data.type === "failed",
  });

  return {
    ...state,
    connected,
  };
}
