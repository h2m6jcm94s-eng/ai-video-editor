// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useEffect, useState, useRef } from "react";

interface ProgressState {
  stage: string;
  progress: number;
  message: string;
  connected: boolean;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";
const MAX_RECONNECT_ATTEMPTS = 5;

export function useProgress(jobId: string | null) {
  const [state, setState] = useState<ProgressState>({
    stage: "",
    progress: 0,
    message: "",
    connected: false,
  });
  const attemptsRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!jobId) return;
    attemptsRef.current = 0;

    const connect = () => {
      if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setState((prev) => ({ ...prev, connected: false, message: "Reconnect limit reached. Refresh to retry." }));
        return;
      }

      const eventSource = new EventSource(`${API_BASE}/progress/${jobId}/events`, { withCredentials: true });

      eventSource.onopen = () => {
        attemptsRef.current = 0;
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
        eventSource.close();
        attemptsRef.current += 1;
        setState((prev) => ({ ...prev, connected: false }));
        const delay = Math.min(2 ** attemptsRef.current * 1000, 30000);
        timeoutRef.current = setTimeout(connect, delay);
      };

      return eventSource;
    };

    const eventSource = connect();

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible" && eventSource?.readyState === EventSource.CLOSED) {
        connect();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      eventSource?.close();
    };
  }, [jobId]);

  return state;
}
