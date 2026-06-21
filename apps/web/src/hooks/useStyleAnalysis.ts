// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";

interface StyleAnalysisState {
  analysis: Record<string, unknown> | null;
  loading: boolean;
  isPending: boolean;
  error: string | null;
  refresh: () => Promise<Record<string, unknown> | null>;
}

const POLL_INTERVAL_MS = 5000;

export function useStyleAnalysis(projectId: string): StyleAnalysisState {
  const api = useApi();
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchStyle = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!silent) setLoading(true);
      setError(null);
      try {
        const res = await api.projects.getStyle(projectId);
        setAnalysis(res.styleAnalysis ?? null);
        setIsPending(false);
        return res.styleAnalysis ?? null;
      } catch (err) {
        if (err instanceof APIError && err.code === "PENDING") {
          setIsPending(true);
          setAnalysis(null);
          return null;
        }
        const message = err instanceof Error ? err.message : "Failed to load style analysis";
        setError(message);
        setIsPending(false);
        return null;
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [api, projectId],
  );

  const refresh = useCallback((): ReturnType<typeof fetchStyle> => {
    return fetchStyle();
  }, [fetchStyle]);

  useEffect(() => {
    void fetchStyle();
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [fetchStyle]);

  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (!isPending) return;
    pollRef.current = setInterval(() => {
      void fetchStyle({ silent: true });
    }, POLL_INTERVAL_MS);
  }, [isPending, fetchStyle]);

  return { analysis, loading, isPending, error, refresh };
}
