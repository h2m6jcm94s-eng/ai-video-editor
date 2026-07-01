"use client";

import { AlertTriangle, Check, CheckCheck, Info, X } from "lucide-react";
import { useNotifications } from "@/hooks/useNotifications";

interface NotificationPanelProps {
  onClose: () => void;
}

function isError(code: string) {
  return code.includes("ERROR") || code.includes("FAIL");
}

export function NotificationPanel({ onClose }: NotificationPanelProps) {
  const { items, isLoading, error, ack, ackAll, refresh } = useNotifications();

  return (
    <div className="dash-noti">
      <div className="dash-noti-head">
        <h3>Notifications</h3>
        <div className="dash-noti-actions">
          {items.length > 0 && (
            <button onClick={ackAll} className="dash-noti-iconbtn" title="Acknowledge all" type="button">
              <CheckCheck />
            </button>
          )}
          <button onClick={onClose} className="dash-noti-iconbtn" title="Close" type="button">
            <X />
          </button>
        </div>
      </div>

      <div className="dash-noti-body">
        {error ? (
          <div className="dash-noti-state err">
            <p>{error}</p>
            <button onClick={refresh} className="dash-noti-retry" type="button">
              Retry
            </button>
          </div>
        ) : isLoading ? (
          <div className="dash-noti-state">Loading…</div>
        ) : items.length === 0 ? (
          <div className="dash-noti-state">No notifications</div>
        ) : (
          items.map((item) => (
            <div key={item.id} className="dash-noti-item">
              <span className={`dash-noti-ico${isError(item.code) ? " err" : ""}`}>
                {isError(item.code) ? <AlertTriangle /> : <Info />}
              </span>
              <div className="dash-noti-msg">
                <p>{item.message}</p>
                <div className="dash-noti-meta">
                  <span>{new Date(item.createdAt).toLocaleTimeString()}</span>
                  {item.occurrenceCount > 1 && (
                    <span className="dash-noti-count">×{item.occurrenceCount}</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => ack(item.id)}
                className="dash-noti-ack"
                title="Acknowledge"
                type="button"
              >
                <Check />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
