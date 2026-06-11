// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useEffect, useRef, useState } from "react";

interface UseSSEOptions<T> {
  url: string;
  enabled?: boolean;
  onEvent: (data: T) => void;
  maxReconnectAttempts?: number;
  fallbackPoll?: () => Promise<T | null>;
  pollIntervalMs?: number;
  shouldClose?: (data: T) => boolean;
}

export function useSSE<T>({
  url,
  enabled = true,
  onEvent,
  maxReconnectAttempts = 5,
  fallbackPoll,
  pollIntervalMs = 3000,
  shouldClose,
}: UseSSEOptions<T>) {
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const attemptsRef = useRef(0);
  const lastEventIdRef = useRef<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    if (!enabled) return;
    mountedRef.current = true;
    attemptsRef.current = 0;

    const startPolling = () => {
      if (pollRef.current || !fallbackPoll) return;
      pollRef.current = setInterval(async () => {
        if (!mountedRef.current) return;
        const data = await fallbackPoll().catch(() => null);
        if (data) onEvent(data);
      }, pollIntervalMs);
    };

    const stopPolling = () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    const connect = () => {
      if (attemptsRef.current >= maxReconnectAttempts) {
        startPolling();
        return;
      }
      const fullUrl = lastEventIdRef.current
        ? `${url}${url.includes("?") ? "&" : "?"}lastEventId=${lastEventIdRef.current}`
        : url;
      const es = new EventSource(fullUrl, { withCredentials: true });
      esRef.current = es;
      es.onopen = () => {
        if (!mountedRef.current) return;
        attemptsRef.current = 0;
        stopPolling();
        setConnected(true);
      };
      es.onmessage = (e) => {
        if (!mountedRef.current) return;
        lastEventIdRef.current = e.lastEventId || lastEventIdRef.current;
        try {
          const data = JSON.parse(e.data) as T;
          onEvent(data);
          if (shouldClose?.(data)) {
            es.close();
            setConnected(false);
          }
        } catch (e) {
          // eslint-disable-next-line no-console
          console.warn("[useSSE] Failed to parse event data:", e);
        }
      };
      es.onerror = () => {
        es.close();
        if (!mountedRef.current) return;
        setConnected(false);
        attemptsRef.current += 1;
        const delay = Math.min(2 ** attemptsRef.current * 1000, 30000);
        timeoutRef.current = setTimeout(connect, delay);
      };
    };

    const handleVis = () => {
      if (document.hidden) {
        esRef.current?.close();
        setConnected(false);
      } else if (!esRef.current || esRef.current.readyState === EventSource.CLOSED) {
        attemptsRef.current = 0;
        connect();
      }
    };

    document.addEventListener("visibilitychange", handleVis);
    connect();

    return () => {
      mountedRef.current = false;
      document.removeEventListener("visibilitychange", handleVis);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      stopPolling();
      esRef.current?.close();
    };
  }, [url, enabled, onEvent, maxReconnectAttempts, fallbackPoll, pollIntervalMs, shouldClose]);

  return { connected };
}
