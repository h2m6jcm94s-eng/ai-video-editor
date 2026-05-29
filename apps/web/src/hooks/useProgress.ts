"use client";

import { useEffect, useState, useCallback } from "react";

interface ProgressState {
  stage: string;
  progress: number;
  message: string;
  connected: boolean;
}

export function useProgress(jobId: string | null) {
  const [state, setState] = useState<ProgressState>({
    stage: "",
    progress: 0,
    message: "",
    connected: false,
  });

  useEffect(() => {
    if (!jobId) return;

    const eventSource = new EventSource(`/api/progress/${jobId}/events`);

    eventSource.onopen = () => {
      setState((prev) => ({ ...prev, connected: true }));
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "connected") return;

        setState({
          stage: data.stage || "",
          progress: data.progress || 0,
          message: data.message || "",
          connected: true,
        });
      } catch {
        // Heartbeat or non-JSON
      }
    };

    eventSource.onerror = () => {
      setState((prev) => ({ ...prev, connected: false }));
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [jobId]);

  return state;
}
