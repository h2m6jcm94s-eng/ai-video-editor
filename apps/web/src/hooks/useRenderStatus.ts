// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";
import type { RenderJob } from "@/types/api";

const ACTIVE_STATUSES = ["queued", "running"] as const;

interface RenderStatus {
  activeRender: RenderJob | null;
  isRendering: boolean;
  isLoading: boolean;
}

export function useRenderStatus(projectId: string): RenderStatus {
  const api = useApi();
  const [activeRender, setActiveRender] = useState<RenderJob | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeRenderRef = useRef(activeRender);

  // Keep ref in sync with state so callbacks see latest value
  useEffect(() => {
    activeRenderRef.current = activeRender;
  }, [activeRender]);

  const poll = useCallback(async () => {
    try {
      const { jobs } = await api.renders.listByProject(projectId);
      const active = jobs.find((j: RenderJob) =>
        ACTIVE_STATUSES.includes(j.status as (typeof ACTIVE_STATUSES)[number]),
      );
      setActiveRender(active || null);
    } catch {
      // Silently ignore polling errors — the next poll will retry
    } finally {
      setIsLoading(false);
    }
  }, [projectId, api]);

  useEffect(() => {
    let mounted = true;

    const doPoll = async () => {
      if (!mounted) return;
      await poll();
      if (!mounted) return;
      const hasActive = activeRenderRef.current !== null;
      if (hasActive && !intervalRef.current) {
        intervalRef.current = setInterval(() => {
          if (mounted) poll();
        }, 3000);
      } else if (!hasActive && intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    doPoll();

    return () => {
      mounted = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [projectId, poll]);

  return {
    activeRender,
    isRendering: !!activeRender,
    isLoading,
  };
}
