"use client";

import { AlertTriangle, Check, CheckCheck, Info, X } from "lucide-react";
import { useNotifications } from "@/hooks/useNotifications";

interface NotificationPanelProps {
  onClose: () => void;
}

function getIconForCode(code: string) {
  if (code.includes("ERROR") || code.includes("FAIL")) {
    return <AlertTriangle className="h-4 w-4 text-red-400" />;
  }
  return <Info className="h-4 w-4 text-blue-400" />;
}

export function NotificationPanel({ onClose }: NotificationPanelProps) {
  const { items, isLoading, ack, ackAll } = useNotifications();

  return (
    <div className="absolute right-0 top-full mt-2 w-80 rounded-lg border bg-popover shadow-lg z-50">
      <div className="flex items-center justify-between p-3 border-b">
        <h3 className="font-semibold text-sm">Notifications</h3>
        <div className="flex items-center gap-1">
          {items.length > 0 && (
            <button
              onClick={ackAll}
              className="p-1.5 rounded hover:bg-accent transition-colors"
              title="Acknowledge all"
            >
              <CheckCheck className="h-4 w-4" />
            </button>
          )}
          <button onClick={onClose} className="p-1.5 rounded hover:bg-accent transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="max-h-72 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 text-center text-sm text-muted-foreground">Loading...</div>
        ) : items.length === 0 ? (
          <div className="p-4 text-center text-sm text-muted-foreground">No notifications</div>
        ) : (
          <ul className="divide-y">
            {items.map((item) => (
              <li key={item.id} className="flex items-start gap-2 p-3 hover:bg-accent/50 transition-colors">
                <div className="mt-0.5 shrink-0">{getIconForCode(item.code)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm leading-snug">{item.message}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-muted-foreground">
                      {new Date(item.createdAt).toLocaleTimeString()}
                    </span>
                    {item.occurrenceCount > 1 && (
                      <span className="text-xs bg-muted px-1.5 py-0.5 rounded-full">
                        × {item.occurrenceCount}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => ack(item.id)}
                  className="p-1 rounded hover:bg-accent transition-colors shrink-0"
                  title="Acknowledge"
                >
                  <Check className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
