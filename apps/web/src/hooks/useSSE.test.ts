// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSSE } from "./useSSE";

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  url: string;
  withCredentials: boolean;
  readyState = FakeEventSource.CONNECTING;
  onopen: ((this: FakeEventSource, ev: Event) => void) | null = null;
  onmessage: ((this: FakeEventSource, ev: MessageEvent) => void) | null = null;
  onerror: ((this: FakeEventSource, ev: Event) => void) | null = null;

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = init?.withCredentials ?? false;
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
}

describe("useSSE", () => {
  let instances: FakeEventSource[] = [];

  beforeEach(() => {
    instances = [];
    const ctor = vi.fn(function (this: FakeEventSource, url: string, init?: { withCredentials?: boolean }) {
      const es = new FakeEventSource(url, init);
      instances.push(es);
      return es;
    }) as unknown as typeof EventSource;
    (ctor as unknown as Record<string, number>).CONNECTING = FakeEventSource.CONNECTING;
    (ctor as unknown as Record<string, number>).OPEN = FakeEventSource.OPEN;
    (ctor as unknown as Record<string, number>).CLOSED = FakeEventSource.CLOSED;
    vi.stubGlobal("EventSource", ctor);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("opens EventSource when enabled and jobId provided", () => {
    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        enabled: true,
        onEvent: vi.fn(),
      }),
    );
    expect(EventSource).toHaveBeenCalledWith("http://localhost/api/progress/job-1/events", {
      withCredentials: true,
    });
  });

  it("does not open EventSource when disabled", () => {
    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        enabled: false,
        onEvent: vi.fn(),
      }),
    );
    expect(EventSource).not.toHaveBeenCalled();
  });

  it("sets connected=true on open", async () => {
    const onEvent = vi.fn();
    const { result } = renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        onEvent,
      }),
    );

    const es = instances[0];
    es.readyState = FakeEventSource.OPEN;
    es.onopen?.call(es, new Event("open"));

    await waitFor(() => expect(result.current.connected).toBe(true));
  });

  it("calls onEvent with parsed JSON data", async () => {
    const onEvent = vi.fn();
    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        onEvent,
      }),
    );

    const es = instances[0];
    const messageEvent = new MessageEvent("message", {
      data: JSON.stringify({ type: "progress", progress: 42 }),
      lastEventId: "1",
    });
    es.onmessage?.call(es, messageEvent);

    await waitFor(() => expect(onEvent).toHaveBeenCalledWith({ type: "progress", progress: 42 }));
  });

  it("reconnects with exponential backoff on error", async () => {
    vi.useFakeTimers();
    const onEvent = vi.fn();
    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        onEvent,
        maxReconnectAttempts: 3,
      }),
    );

    const es = instances[0];
    es.onerror?.call(es, new Event("error"));

    // First reconnect after 2s (2^1 * 1000)
    await vi.advanceTimersByTimeAsync(2000);
    expect(instances.length).toBe(2);

    // Second reconnect after 4s (2^2 * 1000)
    instances[1].onerror?.call(instances[1], new Event("error"));
    await vi.advanceTimersByTimeAsync(4000);
    expect(instances.length).toBe(3);
  });

  it("stops reconnecting after max attempts and starts polling fallback", async () => {
    vi.useFakeTimers();
    const fallbackPoll = vi.fn().mockResolvedValue({ type: "poll", progress: 50 });
    const onEvent = vi.fn();

    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        onEvent,
        maxReconnectAttempts: 2,
        fallbackPoll,
        pollIntervalMs: 3000,
      }),
    );

    // Exhaust both reconnect attempts
    instances[0].onerror?.call(instances[0], new Event("error"));
    await vi.advanceTimersByTimeAsync(2000);
    instances[1].onerror?.call(instances[1], new Event("error"));
    await vi.advanceTimersByTimeAsync(4000);
    expect(instances.length).toBe(2);

    // Polling should kick in
    await vi.advanceTimersByTimeAsync(3000);
    expect(fallbackPoll).toHaveBeenCalled();
    expect(onEvent).toHaveBeenCalledWith({ type: "poll", progress: 50 });
  });

  it("closes EventSource on tab hide", async () => {
    let hidden = false;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => hidden,
    });

    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        onEvent: vi.fn(),
      }),
    );

    const es = instances[0];
    hidden = true;
    document.dispatchEvent(new Event("visibilitychange"));

    await waitFor(() => expect(es.readyState).toBe(FakeEventSource.CLOSED));
  });

  it("reopens EventSource on tab show with lastEventId in URL", async () => {
    let hidden = false;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => hidden,
    });

    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        onEvent: vi.fn(),
      }),
    );

    const es = instances[0];
    const messageEvent = new MessageEvent("message", {
      data: JSON.stringify({ type: "progress" }),
      lastEventId: "7",
    });
    es.onmessage?.call(es, messageEvent);

    hidden = true;
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    hidden = false;
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    await waitFor(() => {
      expect(instances.length).toBe(2);
      expect(instances[1].url).toContain("lastEventId=7");
    });
  });

  it("calls shouldClose and closes EventSource when predicate returns true", async () => {
    const onEvent = vi.fn();
    const shouldClose = vi.fn().mockReturnValue(true);

    renderHook(() =>
      useSSE({
        url: "http://localhost/api/progress/job-1/events",
        onEvent,
        shouldClose,
      }),
    );

    const es = instances[0];
    const messageEvent = new MessageEvent("message", {
      data: JSON.stringify({ type: "complete" }),
    });
    es.onmessage?.call(es, messageEvent);

    await waitFor(() => expect(shouldClose).toHaveBeenCalledWith({ type: "complete" }));
    expect(es.readyState).toBe(FakeEventSource.CLOSED);
  });
});
