"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

interface NotificationEvent {
  id: string;
  code: string;
  message: string;
  occurrenceCount: number;
  createdAt: string;
}

interface NotificationItem {
  id: string;
  code: string;
  message: string;
  occurrenceCount: number;
  createdAt: string;
  acknowledged: boolean;
}

interface UseNotificationsReturn {
  items: NotificationItem[];
  unreadCount: number;
  isLoading: boolean;
  error: string | null;
  ack: (id: string) => Promise<void>;
  ackAll: () => Promise<void>;
  refresh: () => Promise<void>;
}

function isAuthError(status: number) {
  return status === 401 || status === 403;
}

export function useNotifications(): UseNotificationsReturn {
  const { getToken, isSignedIn } = useAuth();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  const fetchNotifications = useCallback(async () => {
    if (!isSignedIn) return;
    setIsLoading(true);
    setError(null);
    try {
      // Pull token inside the callback; Clerk's getToken reference is unstable.
      const token = await getToken();
      const res = await fetch("/api/notifications", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
      } else if (isAuthError(res.status)) {
        setError("Session expired. Please sign in again.");
      } else {
        setError("Failed to load notifications.");
      }
    } catch (e) {
      setError("Failed to load notifications.");
      // eslint-disable-next-line no-console
      console.warn("[useNotifications] Fetch failed:", e);
    } finally {
      setIsLoading(false);
    }
    // getToken reference is intentionally unstable; do not add to deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // SSE for live updates
  useEffect(() => {
    if (!isSignedIn) return;

    const es = new EventSource("/api/notifications/events", {
      withCredentials: true,
    });
    sseRef.current = es;

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.type === "notification") {
          setItems((prev) => [parsed.data, ...prev]);
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn("[useNotifications] SSE parse failed:", e);
      }
    };

    es.onerror = () => {
      // Auto-reconnect is built into EventSource
    };

    return () => {
      es.close();
      sseRef.current = null;
    };
  }, [isSignedIn]);

  const ack = useCallback(
    async (id: string) => {
      const previous = items;
      setItems((prev) => prev.filter((i) => i.id !== id));
      try {
        const token = await getToken();
        const res = await fetch(`/api/notifications/${id}/ack`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          throw new Error(`Ack failed: ${res.status}`);
        }
      } catch (e) {
        setItems(previous);
        setError("Failed to dismiss notification.");
        // eslint-disable-next-line no-console
        console.warn("[useNotifications] Ack failed:", e);
      }
    },
    // getToken reference is intentionally unstable; do not add to deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items],
  );

  const ackAll = useCallback(
    async () => {
      const previous = items;
      setItems([]);
      try {
        const token = await getToken();
        const res = await fetch("/api/notifications/ack-all", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          throw new Error(`Ack-all failed: ${res.status}`);
        }
      } catch (e) {
        setItems(previous);
        setError("Failed to dismiss all notifications.");
        // eslint-disable-next-line no-console
        console.warn("[useNotifications] Ack-all failed:", e);
      }
    },
    // getToken reference is intentionally unstable; do not add to deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items],
  );

  const unreadCount = items.filter((i) => !i.acknowledged).length;

  return {
    items,
    unreadCount,
    isLoading,
    error,
    ack,
    ackAll,
    refresh: fetchNotifications,
  };
}
