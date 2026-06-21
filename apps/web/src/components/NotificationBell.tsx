"use client";

import { Bell } from "lucide-react";
import React, { useState } from "react";
import { useNotifications } from "@/hooks/useNotifications";
import { NotificationPanel } from "./NotificationPanel";

interface NotificationBellContentProps {
  onClick: () => void;
  unreadCount: number;
}

function NotificationBellContent({ onClick, unreadCount }: NotificationBellContentProps) {
  return (
    <button
      onClick={onClick}
      className="relative rounded-full p-2 hover:bg-accent transition-colors"
      aria-label="Notifications"
    >
      <Bell className="h-5 w-5" />
      {unreadCount > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
    </button>
  );
}

class NotificationErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <button
          className="relative rounded-full p-2 text-muted-foreground hover:bg-accent transition-colors"
          aria-label="Notifications unavailable"
          disabled
        >
          <Bell className="h-5 w-5" />
        </button>
      );
    }
    return this.props.children;
  }
}

function NotificationBellInner() {
  const [open, setOpen] = useState(false);
  const { unreadCount } = useNotifications();

  return (
    <div className="relative">
      <NotificationBellContent onClick={() => setOpen(!open)} unreadCount={unreadCount} />
      {open && <NotificationPanel onClose={() => setOpen(false)} />}
    </div>
  );
}

export function NotificationBell() {
  return (
    <NotificationErrorBoundary>
      <NotificationBellInner />
    </NotificationErrorBoundary>
  );
}
