import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { APIError } from "@/lib/api/error";
import type { CutList } from "@/types/api";
import { useAutosave } from "./useAutosave";

const { updateCutlist } = vi.hoisted(() => ({ updateCutlist: vi.fn() }));
const api = { projects: { updateCutlist } };

vi.mock("@/lib/api/client", () => ({
  useApi: () => api,
}));

const baseCutList: CutList = {
  globals: {
    totalDurationS: 10,
    tempoBpm: 120,
    timeSignature: "4/4",
    energyCurve: [0.5],
    sectionMarkers: [{ name: "full", startS: 0, endS: 10 }],
    aspectRatio: "9:16",
  },
  slots: [
    {
      index: 0,
      startS: 0,
      durationS: 10,
      beatIndex: 0,
      section: "full",
      transitionIn: "hard_cut",
      transitionOut: "hard_cut",
      targetShotType: "medium",
      subjectHint: "person",
      motionHint: "static",
      energyLevel: 0.5,
      requiredTags: [],
      avoidTags: [],
      maskEnabled: true,
      identityIdsPresent: [],
      protagonistMatteEnabled: true,
      enableKineticText: false,
      textZLayer: "on_top",
      textDensity: "medium",
      effects: [],
      sourceWindowStartS: undefined,
      anticipationOffsetS: 0,
    },
  ],
  overlays: [],
  audioTracks: [],
};

const changedCutList: CutList = {
  ...baseCutList,
  globals: { ...baseCutList.globals, totalDurationS: 12 },
};

describe("useAutosave", () => {
  beforeEach(() => {
    updateCutlist.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const setup = (onRollback: (cl: CutList) => void) =>
    renderHook((props) => useAutosave(props), {
      initialProps: {
        projectId: "p1",
        cutList: baseCutList,
        onRollback,
        debounceMs: 500,
      },
    });

  it("saves after the debounce window", async () => {
    updateCutlist.mockResolvedValueOnce({ project: { id: "p1" } });
    const onRollback = vi.fn();
    const { result, rerender } = setup(onRollback);

    rerender({ projectId: "p1", cutList: changedCutList, onRollback, debounceMs: 500 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(result.current.state.status).toBe("saved");
    expect(updateCutlist).toHaveBeenCalledWith("p1", changedCutList);
    expect(onRollback).not.toHaveBeenCalled();
  });

  it("does not roll back on a generic network error", async () => {
    updateCutlist.mockRejectedValueOnce(new Error("network down"));
    const onRollback = vi.fn();
    const { result, rerender } = setup(onRollback);

    rerender({ projectId: "p1", cutList: changedCutList, onRollback, debounceMs: 500 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(result.current.state.status).toBe("error");
    expect(onRollback).not.toHaveBeenCalled();
  });

  it("rolls back on a conflict response", async () => {
    updateCutlist.mockRejectedValueOnce(new APIError(409, "CONFLICT", "conflict"));
    const onRollback = vi.fn();
    const { result, rerender } = setup(onRollback);

    rerender({ projectId: "p1", cutList: changedCutList, onRollback, debounceMs: 500 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(result.current.state.status).toBe("error");
    expect(onRollback).toHaveBeenCalledWith(baseCutList);
  });

  it("allows retrying the last pending cutlist", async () => {
    updateCutlist
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce({ project: { id: "p1" } });

    const onRollback = vi.fn();
    const { result, rerender } = setup(onRollback);

    rerender({ projectId: "p1", cutList: changedCutList, onRollback, debounceMs: 500 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.state.status).toBe("error");

    act(() => result.current.retry());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.state.status).toBe("saved");
    expect(updateCutlist).toHaveBeenCalledTimes(2);
    expect(updateCutlist).toHaveBeenLastCalledWith("p1", changedCutList);
    expect(onRollback).not.toHaveBeenCalled();
  });

  it("rolls back on retry only when the retry itself returns a conflict", async () => {
    updateCutlist
      .mockRejectedValueOnce(new Error("network down"))
      .mockRejectedValueOnce(new APIError(409, "CONCURRENT_EDIT", "locked"));
    const onRollback = vi.fn();
    const { result, rerender } = setup(onRollback);

    rerender({ projectId: "p1", cutList: changedCutList, onRollback, debounceMs: 500 });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(result.current.state.status).toBe("error");
    expect(onRollback).not.toHaveBeenCalled();

    act(() => result.current.retry());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.state.status).toBe("error");
    expect(onRollback).toHaveBeenCalledTimes(1);
  });
});
