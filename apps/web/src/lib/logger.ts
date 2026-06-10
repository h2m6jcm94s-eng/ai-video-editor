// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.

type LogLevel = "debug" | "info" | "warn" | "error";

interface LogEvent {
  level: LogLevel;
  message: string;
  context?: Record<string, unknown>;
  ts: number;
  userId?: string;
  url: string;
}

class Logger {
  private buf: LogEvent[] = [];
  private flushTimer: ReturnType<typeof setTimeout> | null = null;

  log(level: LogLevel, message: string, context?: Record<string, unknown>) {
    const event: LogEvent = {
      level,
      message,
      context,
      ts: Date.now(),
      url: typeof window !== "undefined" ? window.location.pathname : "",
    };
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console[level === "debug" ? "log" : level](message, context);
    }
    this.buf.push(event);
    if (this.buf.length >= 10) this.flush();
    else if (!this.flushTimer) this.flushTimer = setTimeout(() => this.flush(), 5000);
  }

  async flush() {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    if (this.buf.length === 0) return;
    const events = this.buf.splice(0);
    try {
      await fetch("/api/log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events }),
        keepalive: true,
      });
    } catch {
      // Re-buffer on failure
      this.buf.unshift(...events);
    }
  }

  debug = (m: string, c?: Record<string, unknown>) => this.log("debug", m, c);
  info = (m: string, c?: Record<string, unknown>) => this.log("info", m, c);
  warn = (m: string, c?: Record<string, unknown>) => this.log("warn", m, c);
  error = (m: string, c?: Record<string, unknown>) => this.log("error", m, c);
}

export const logger = new Logger();

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => logger.flush());
}
