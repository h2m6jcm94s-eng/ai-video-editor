// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";
import type { RenderJob } from "@/types/api";

const ACTIVE_STATUSES = ["queued", "running"] as const;

interface RenderStatus {
  activeRender: RenderJob | null;
  latestRender: RenderJob | null;
  isRendering: boolean;
  isLoading: boolean;
}

export function useRenderStatus(projectId: string): RenderStatus {
  const api = useApi();
  const [activeRender, setActiveRender] = useState<RenderJob | null>(null);
  const [latestRender, setLatestRender] = useState<RenderJob | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const { jobs } = await api.renders.listByProject(projectId);
      const active = jobs.find((j: RenderJob) =>
        ACTIVE_STATUSES.includes(j.status as (typeof ACTIVE_STATUSES)[number]),
      );
      setActiveRender(active || null);
      // Track most recent completed or failed render
      const done = jobs
        .filter((j: RenderJob) => j.status === "complete" || j.status === "failed")
        .sort(
          (a: RenderJob, b: RenderJob) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        )[0];
      if (done) setLatestRender(done);
    } catch (err) {
      console.error("Render status poll failed:", err);
    } finally {
      setIsLoading(false);
    }
    // api is kept stable by useApi(); projectId is the only real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    let mounted = true;

    const doPoll = async () => {
      if (!mounted) return;
      await poll();
    };

    doPoll();
    intervalRef.current = setInterval(() => {
      if (mounted) poll();
    }, 3000);

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
    latestRender,
    isRendering: !!activeRender,
    isLoading,
  };
}
