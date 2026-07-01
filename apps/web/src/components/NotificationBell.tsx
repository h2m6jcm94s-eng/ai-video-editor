"use client";

import { Bell } from "lucide-react";
import React, { useState } from "react";
import { useNotifications } from "@/hooks/useNotifications";
import { NotificationPanel } from "./NotificationPanel";

interface NotificationBellStyle {
  /** Overrides the trigger button's classes when provided. */
  className?: string;
  /** Overrides the unread-count badge's classes when provided. */
  badgeClassName?: string;
}

const DEFAULT_BUTTON_CLASS = "relative rounded-full p-2 hover:bg-accent transition-colors";
const DEFAULT_BADGE_CLASS =
  "absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white";

interface NotificationBellContentProps extends NotificationBellStyle {
  onClick: () => void;
  unreadCount: number;
}

function NotificationBellContent({
  onClick,
  unreadCount,
  className,
  badgeClassName,
}: NotificationBellContentProps) {
  return (
    <button onClick={onClick} className={className ?? DEFAULT_BUTTON_CLASS} aria-label="Notifications">
      <Bell className="h-5 w-5" />
      {unreadCount > 0 && (
        <span className={badgeClassName ?? DEFAULT_BADGE_CLASS}>
          {unreadCount > 99 ? "99+" : unreadCount}
        </span>
      )}
    </button>
  );
}

class NotificationErrorBoundary extends React.Component<
  { children: React.ReactNode; fallbackClassName?: string },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode; fallbackClassName?: string }) {
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
          className={
            this.props.fallbackClassName ??
            "relative rounded-full p-2 text-muted-foreground hover:bg-accent transition-colors"
          }
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

function NotificationBellInner({ className, badgeClassName }: NotificationBellStyle) {
  const [open, setOpen] = useState(false);
  const { unreadCount } = useNotifications();

  return (
    <div className="relative">
      <NotificationBellContent
        onClick={() => setOpen(!open)}
        unreadCount={unreadCount}
        className={className}
        badgeClassName={badgeClassName}
      />
      {open && <NotificationPanel onClose={() => setOpen(false)} />}
    </div>
  );
}

export function NotificationBell({ className, badgeClassName }: NotificationBellStyle = {}) {
  return (
    <NotificationErrorBoundary fallbackClassName={className}>
      <NotificationBellInner className={className} badgeClassName={badgeClassName} />
    </NotificationErrorBoundary>
  );
}
