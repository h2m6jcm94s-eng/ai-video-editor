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
  ack: (id: string) => Promise<void>;
  ackAll: () => Promise<void>;
  refresh: () => Promise<void>;
}

export function useNotifications(): UseNotificationsReturn {
  const { getToken, isSignedIn } = useAuth();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const sseRef = useRef<EventSource | null>(null);

  const fetchNotifications = useCallback(async () => {
    if (!isSignedIn) return;
    setIsLoading(true);
    try {
      const token = await getToken();
      const res = await fetch("/api/notifications", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("[useNotifications] Fetch failed:", e);
    } finally {
      setIsLoading(false);
    }
  }, [getToken, isSignedIn]);

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
      const token = await getToken();
      await fetch(`/api/notifications/${id}/ack`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      setItems((prev) => prev.filter((i) => i.id !== id));
    },
    [getToken],
  );

  const ackAll = useCallback(async () => {
    const token = await getToken();
    await fetch("/api/notifications/ack-all", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    setItems([]);
  }, [getToken]);

  const unreadCount = items.filter((i) => !i.acknowledged).length;

  return {
    items,
    unreadCount,
    isLoading,
    ack,
    ackAll,
    refresh: fetchNotifications,
  };
}
