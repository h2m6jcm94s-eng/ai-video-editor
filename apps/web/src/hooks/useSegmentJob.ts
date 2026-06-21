// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";

interface SegmentState {
  workflowId: string | null;
  result: Record<string, unknown> | null;
  loading: boolean;
  error: string | null;
}

export function useSegmentJob(projectId: string) {
  const api = useApi();
  const [state, setState] = useState<SegmentState>({
    workflowId: null,
    result: null,
    loading: false,
    error: null,
  });
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const start = useCallback(
    async (assetId: string, prompt: string, mode: "image" | "video" = "image") => {
      clearPoll();
      setState({ workflowId: null, result: null, loading: true, error: null });
      try {
        const { workflowId } = await api.segments.start({ projectId, assetId, prompt, mode });
        setState((s) => ({ ...s, workflowId }));
        return workflowId;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Segmentation failed to start";
        setState((s) => ({ ...s, loading: false, error: message }));
        return null;
      }
    },
    [api, projectId, clearPoll],
  );

  useEffect(() => {
    if (!state.workflowId || state.result) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.segments.get(state.workflowId as string);
        const result = res.result;
        const status = result?.status as string | undefined;
        if (status === "completed" || status === "skipped" || result?.available === false) {
          clearPoll();
          setState((s) => ({ ...s, result, loading: false }));
        }
      } catch (err) {
        // keep polling; surface on final stop
      }
    }, 3000);
    return clearPoll;
  }, [state.workflowId, state.result, api, clearPoll]);

  const reset = useCallback(() => {
    clearPoll();
    setState({ workflowId: null, result: null, loading: false, error: null });
  }, [clearPoll]);

  return { ...state, start, reset };
}
