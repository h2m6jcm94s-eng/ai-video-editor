// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useCallback, useState } from "react";
import { useApi } from "@/lib/api/client";
import type { RenderJob } from "@/types/api";
import { useSSE } from "./useSSE";

interface RenderEvent {
  type: string;
  stage?: string;
  progress?: number;
  jobId?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

export function useRenderEvents(jobId: string | null) {
  const api = useApi();
  const [events, setEvents] = useState<RenderEvent[]>([]);

  const push = useCallback((e: RenderEvent) => {
    // Functional update avoids stale ref reads during React batching.
    setEvents((prev) => [...prev, e]);
  }, []);

  const fallbackPoll = useCallback(async () => {
    if (!jobId) return null;
    const { job } = await api.renders.get(jobId);
    if (!job) return null;
    const ev: RenderEvent = {
      type: "poll",
      stage: job.stage,
      progress: job.progress,
      jobId: job.id,
    };
    push(ev);
    return ev;
  }, [jobId, api, push]);

  const handleEvent = useCallback(
    (data: RenderEvent) => {
      push(data);
    },
    [push],
  );

  const { connected } = useSSE<RenderEvent>({
    url: jobId ? `${API_BASE}/progress/${jobId}/events` : "",
    enabled: !!jobId,
    onEvent: handleEvent,
    maxReconnectAttempts: 5,
    fallbackPoll,
    pollIntervalMs: 3000,
    shouldClose: (data) => data.type === "complete" || data.type === "failed",
  });

  return { events, connected };
}
