// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";
import type { RenderJob } from "@/types/api";

interface RenderEvent {
  type: string;
  stage?: string;
  progress?: number;
  jobId?: string;
}

export function useRenderEvents(jobId: string | null) {
  const api = useApi();
  const [events, setEvents] = useState<RenderEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId) return;

    let mounted = true;
    const eventsSoFar: RenderEvent[] = [];

    const push = (e: RenderEvent) => {
      if (!mounted) return;
      eventsSoFar.push(e);
      setEvents([...eventsSoFar]);
    };

    const startPolling = () => {
      if (intervalRef.current) return;
      intervalRef.current = setInterval(async () => {
        if (!mounted || !jobId) return;
        try {
          const { job } = await api.renders.get(jobId);
          if (job) {
            push({
              type: "poll",
              stage: job.stage,
              progress: job.progress,
              jobId: job.id,
            });
            if (job.status === "complete" || job.status === "failed") {
              clearInterval(intervalRef.current!);
              intervalRef.current = null;
            }
          }
        } catch {
          // Polling errors are silent — next interval retries
        }
      }, 3000);
    };

    const startSSE = () => {
      try {
        const es = api.progress.subscribe(jobId);
        esRef.current = es;

        es.addEventListener("open", () => {
          if (!mounted) return;
          setConnected(true);
        });

        es.addEventListener("message", (e) => {
          if (!mounted) return;
          try {
            const data = JSON.parse(e.data);
            push(data);
            if (data.type === "complete" || data.type === "failed") {
              es.close();
            }
          } catch {
            push({ type: "raw", jobId });
          }
        });

        es.addEventListener("error", () => {
          if (!mounted) return;
          setConnected(false);
          es.close();
          // Fallback to polling on SSE error
          startPolling();
        });
      } catch {
        // SSE not supported or failed immediately — fall back to polling
        startPolling();
      }
    };

    startSSE();

    return () => {
      mounted = false;
      esRef.current?.close();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [jobId, api]);

  return { events, connected };
}
