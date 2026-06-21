// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCountUp } from "./useCountUp";

describe("useCountUp", () => {
  let rafSpy: ReturnType<typeof vi.spyOn>;
  let rafTime: number;

  beforeEach(() => {
    rafTime = 0;
    rafSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb: FrameRequestCallback) => {
      rafTime += 16;
      cb(rafTime);
      return rafTime;
    });
  });

  afterEach(() => {
    rafSpy.mockRestore();
  });

  it("returns 0 immediately for a target of 0", () => {
    const { result } = renderHook(() => useCountUp(0));
    expect(result.current).toBe(0);
  });

  it("animates to the target value", async () => {
    const { result } = renderHook(() => useCountUp(100, 100));
    await waitFor(() => expect(result.current).toBe(100));
  });

  it("re-animates when the target changes", async () => {
    const { result, rerender } = renderHook(({ target }) => useCountUp(target, 50), {
      initialProps: { target: 10 },
    });
    await waitFor(() => expect(result.current).toBe(10));

    rerender({ target: 20 });
    await waitFor(() => expect(result.current).toBe(20));
  });
});
