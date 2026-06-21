// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";

interface CursorUser {
  userId: string;
  name: string;
  color: string;
  x: number;
  y: number;
}

interface PresenceCursorsProps {
  projectId: string;
  userName: string;
}

const REPORT_DEBOUNCE_MS = 75;

export function PresenceCursors({ projectId, userName }: PresenceCursorsProps) {
  const [users, setUsers] = useState<CursorUser[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const mousePosRef = useRef({ x: 0, y: 0 });
  const reportTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlightControllerRef = useRef<AbortController | null>(null);
  const api = useApi();

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (document.hidden) return;
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      mousePosRef.current = { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) };

      // Abort any in-flight report so we never queue stale positions.
      inFlightControllerRef.current?.abort();
      inFlightControllerRef.current = null;

      if (reportTimeoutRef.current) {
        clearTimeout(reportTimeoutRef.current);
      }

      reportTimeoutRef.current = setTimeout(() => {
        const controller = new AbortController();
        inFlightControllerRef.current = controller;
        api.presence
          .report(
            projectId,
            { x: mousePosRef.current.x, y: mousePosRef.current.y, name: userName },
            { signal: controller.signal },
          )
          .catch((err) => {
            if (err instanceof Error && err.name === "AbortError") return;
            // eslint-disable-next-line no-console
            console.error("Presence report failed:", err);
          })
          .finally(() => {
            if (inFlightControllerRef.current === controller) {
              inFlightControllerRef.current = null;
            }
          });
      }, REPORT_DEBOUNCE_MS);
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      if (reportTimeoutRef.current) {
        clearTimeout(reportTimeoutRef.current);
        reportTimeoutRef.current = null;
      }
      inFlightControllerRef.current?.abort();
      inFlightControllerRef.current = null;
    };
  }, [projectId, userName, api]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    const tick = () => {
      api.presence
        .get(projectId)
        .then((res) => setUsers(res.users))
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.error("Presence fetch failed:", err);
        });
    };
    const start = () => {
      if (interval) return;
      tick();
      interval = setInterval(tick, 1000);
    };
    const stop = () => {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
    };
    const handleVis = () => (document.hidden ? stop() : start());
    if (!document.hidden) start();
    document.addEventListener("visibilitychange", handleVis);
    return () => {
      document.removeEventListener("visibilitychange", handleVis);
      stop();
    };
  }, [projectId, api]);

  if (users.length === 0) return null;

  return (
    <div ref={containerRef} className="absolute inset-0 pointer-events-none z-40 overflow-hidden">
      {users.map((user) => (
        <div
          key={user.userId}
          className="absolute transition-all duration-300 ease-out"
          style={{ left: `${user.x}%`, top: `${user.y}%` }}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="-ml-1 -mt-1">
            <path d="M3 3L16 16L10 17L7 21L3 3Z" fill={user.color} stroke="white" strokeWidth="1.5" />
          </svg>
          <span
            className="absolute left-4 top-3 text-[10px] px-1.5 py-0.5 rounded text-white whitespace-nowrap"
            style={{ backgroundColor: user.color }}
          >
            {user.name}
          </span>
        </div>
      ))}
    </div>
  );
}
