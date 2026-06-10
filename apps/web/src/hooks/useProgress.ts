// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useCallback, useState } from "react";
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

export function useProgress(jobId: string | null) {
  const [state, setState] = useState<ProgressState>({
    stage: "",
    progress: 0,
    message: "",
    connected: false,
  });

  const handleEvent = useCallback((data: ProgressEvent) => {
    if (data.type === "connected") return;
    setState({
      stage: data.stage || "",
      progress: data.progress || 0,
      message: data.message || "",
      connected: true,
    });
  }, []);

  const { connected } = useSSE<ProgressEvent>({
    url: jobId ? `${API_BASE}/progress/${jobId}/events` : "",
    enabled: !!jobId,
    onEvent: handleEvent,
    maxReconnectAttempts: 5,
  });

  return {
    ...state,
    connected,
  };
}
