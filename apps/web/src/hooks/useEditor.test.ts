import type { Effect } from "@ai-video-editor/shared-types";
import { describe, expect, it } from "vitest";
import type { AudioTrack, CanvasOverlay, CutList, Slot } from "@/types/api";
import { editorReducer } from "./useEditor";

function makeCutList(
  slots: Slot[] = [],
  overlays: CanvasOverlay[] = [],
  audioTracks: AudioTrack[] = [],
): CutList {
  return {
    globals: {
      totalDurationS: 30,
      tempoBpm: 120,
      timeSignature: "4/4",
      energyCurve: [],
      sectionMarkers: [],
      aspectRatio: "9:16",
    },
    slots,
    overlays,
    audioTracks,
  };
}

function makeSlot(index: number, overrides: Partial<Slot> = {}): Slot {
  return {
    index,
    startS: index * 5,
    durationS: 5,
    beatIndex: index,
    section: "intro",
    transitionIn: "hard_cut",
    transitionOut: "hard_cut",
    targetShotType: "close_up",
    subjectHint: "person",
    motionHint: "static",
    energyLevel: 0.5,
    requiredTags: [],
    avoidTags: [],
    maskEnabled: true,
    effects: [],
    ...overrides,
  };
}

function makeOverlay(id: string): CanvasOverlay {
  return { id, type: "text", text: "hello", startS: 0, endS: 5, x: 0, y: 0, width: 100, height: 50 };
}

function makeEffect(id: string): Effect {
  return {
    id: `eff-${id}`,
    type: "shake",
    startS: 0,
    durationS: 1,
    params: { intensity: 5, durationMs: 300 },
  };
}

function makeAudioTrack(index: number): AudioTrack {
  return { assetId: `audio-${index}`, gainDb: 0, startS: 0, endS: 30, fadeInS: 0, fadeOutS: 0 };
}

const initialState = {
  cutList: null as CutList | null,
  selectedSlotIndex: null as number | null,
  selectedOverlayId: null as string | null,
  isPlaying: false,
  currentTime: 0,
  zoomLevel: 1,
  assets: [] as any[],
  undoStack: [] as CutList[],
  redoStack: [] as CutList[],
};

describe("editorReducer", () => {
  describe("SET_CUTLIST", () => {
    it("replaces cutList without touching undo/redo", () => {
      const existingUndo = [makeCutList()];
      const state = { ...initialState, undoStack: existingUndo, redoStack: [makeCutList()] };
      const next = editorReducer(state, { type: "SET_CUTLIST", payload: makeCutList([makeSlot(0)]) });
      expect(next.cutList?.slots).toHaveLength(1);
      expect(next.undoStack).toEqual(existingUndo);
      expect(next.redoStack).toHaveLength(1);
    });
  });

  describe("UPDATE_SLOT", () => {
    it("pushes prior state to undoStack and applies patch", () => {
      const cutList = makeCutList([makeSlot(0), makeSlot(1)]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "UPDATE_SLOT", index: 0, slot: { subjectHint: "dog" } });
      expect(next.cutList!.slots[0].subjectHint).toBe("dog");
      expect(next.undoStack).toHaveLength(1);
      expect(next.redoStack).toEqual([]);
    });

    it("is a no-op when cutList is null", () => {
      const next = editorReducer(initialState, {
        type: "UPDATE_SLOT",
        index: 0,
        slot: { subjectHint: "dog" },
      });
      expect(next.cutList).toBeNull();
    });
  });

  describe("ADD_SLOT", () => {
    it("appends a slot and pushes to undo", () => {
      const cutList = makeCutList([makeSlot(0)]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "ADD_SLOT", slot: makeSlot(1) });
      expect(next.cutList!.slots).toHaveLength(2);
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("REMOVE_SLOT", () => {
    it("removes a slot by index", () => {
      const cutList = makeCutList([makeSlot(0), makeSlot(1), makeSlot(2)]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "REMOVE_SLOT", index: 1 });
      expect(next.cutList!.slots).toHaveLength(2);
      expect(next.cutList!.slots[0].index).toBe(0);
      expect(next.cutList!.slots[1].index).toBe(2);
      expect(next.undoStack).toHaveLength(1);
    });

    it("ripples subsequent slots when ripple=true", () => {
      const cutList = makeCutList([
        makeSlot(0, { startS: 0, durationS: 5 }),
        makeSlot(1, { startS: 5, durationS: 5 }),
        makeSlot(2, { startS: 10, durationS: 5 }),
      ]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "REMOVE_SLOT", index: 0, ripple: true });
      expect(next.cutList!.slots[0].startS).toBe(0);
      expect(next.cutList!.slots[1].startS).toBe(5);
    });
  });

  describe("REORDER_SLOTS", () => {
    it("replaces slot order and pushes to undo", () => {
      const cutList = makeCutList([makeSlot(0), makeSlot(1)]);
      const state = { ...initialState, cutList };
      const reordered = [cutList.slots[1], cutList.slots[0]];
      const next = editorReducer(state, { type: "REORDER_SLOTS", slots: reordered });
      expect(next.cutList!.slots[0].index).toBe(1);
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("ADD_OVERLAY", () => {
    it("appends an overlay and pushes to undo", () => {
      const cutList = makeCutList([], [makeOverlay("a")]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "ADD_OVERLAY", overlay: makeOverlay("b") });
      expect(next.cutList!.overlays).toHaveLength(2);
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("UPDATE_OVERLAY", () => {
    it("patches an overlay by id", () => {
      const cutList = makeCutList([], [makeOverlay("a")]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "UPDATE_OVERLAY", id: "a", overlay: { text: "updated" } });
      expect(next.cutList!.overlays[0].text).toBe("updated");
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("REMOVE_OVERLAY", () => {
    it("removes an overlay by id", () => {
      const cutList = makeCutList([], [makeOverlay("a"), makeOverlay("b")]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "REMOVE_OVERLAY", id: "a" });
      expect(next.cutList!.overlays).toHaveLength(1);
      expect(next.cutList!.overlays[0].id).toBe("b");
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("ADD_EFFECT", () => {
    it("adds an effect to a slot", () => {
      const cutList = makeCutList([makeSlot(0)]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "ADD_EFFECT", slotIndex: 0, effect: makeEffect("e1") });
      expect((next.cutList!.slots[0].effects || []).length).toBe(1);
      expect(next.undoStack).toHaveLength(1);
    });

    it("is a no-op for invalid slot index", () => {
      const cutList = makeCutList([makeSlot(0)]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "ADD_EFFECT", slotIndex: 5, effect: makeEffect("e1") });
      expect(next.cutList!.slots[0].effects).toEqual([]);
    });
  });

  describe("REMOVE_EFFECT", () => {
    it("removes an effect from a slot", () => {
      const cutList = makeCutList([makeSlot(0, { effects: [makeEffect("e1"), makeEffect("e2")] })]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "REMOVE_EFFECT", slotIndex: 0, effectId: "eff-e1" });
      expect((next.cutList!.slots[0].effects || []).length).toBe(1);
      expect((next.cutList!.slots[0].effects || [])[0].id).toBe("eff-e2");
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("ADD_AUDIO_TRACK", () => {
    it("appends an audio track", () => {
      const cutList = makeCutList([], [], [makeAudioTrack(0)]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "ADD_AUDIO_TRACK", track: makeAudioTrack(1) });
      expect(next.cutList!.audioTracks).toHaveLength(2);
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("REMOVE_AUDIO_TRACK", () => {
    it("removes an audio track by index", () => {
      const cutList = makeCutList([], [], [makeAudioTrack(0), makeAudioTrack(1)]);
      const state = { ...initialState, cutList };
      const next = editorReducer(state, { type: "REMOVE_AUDIO_TRACK", index: 0 });
      expect(next.cutList!.audioTracks).toHaveLength(1);
      expect((next.cutList!.audioTracks || [])[0].assetId).toBe("audio-1");
      expect(next.undoStack).toHaveLength(1);
    });
  });

  describe("PROMPT_APPLY", () => {
    it("replaces cutList, pushes to undoStack, clears redoStack", () => {
      const oldCutList = makeCutList([makeSlot(0)]);
      const newCutList = makeCutList([makeSlot(0), makeSlot(1)]);
      const state = { ...initialState, cutList: oldCutList, redoStack: [oldCutList] };
      const next = editorReducer(state, { type: "PROMPT_APPLY", cutList: newCutList });
      expect(next.cutList).toEqual(newCutList);
      expect(next.undoStack).toEqual([oldCutList]);
      expect(next.redoStack).toEqual([]);
    });
  });

  describe("UNDO", () => {
    it("pops undoStack to current, pushes current to redoStack", () => {
      const cutListA = makeCutList([makeSlot(0)]);
      const cutListB = makeCutList([makeSlot(0), makeSlot(1)]);
      const state = { ...initialState, cutList: cutListB, undoStack: [cutListA], redoStack: [] };
      const next = editorReducer(state, { type: "UNDO" });
      expect(next.cutList).toEqual(cutListA);
      expect(next.undoStack).toEqual([]);
      expect(next.redoStack).toEqual([cutListB]);
    });

    it("is a no-op when undoStack is empty", () => {
      const cutList = makeCutList([makeSlot(0)]);
      const state = { ...initialState, cutList, undoStack: [], redoStack: [] };
      const next = editorReducer(state, { type: "UNDO" });
      expect(next.cutList).toEqual(cutList);
      expect(next.undoStack).toEqual([]);
      expect(next.redoStack).toEqual([]);
    });
  });

  describe("REDO", () => {
    it("pops redoStack to current, pushes current to undoStack", () => {
      const cutListA = makeCutList([makeSlot(0)]);
      const cutListB = makeCutList([makeSlot(0), makeSlot(1)]);
      const state = {
        ...initialState,
        cutList: cutListA as CutList | null,
        undoStack: [],
        redoStack: [cutListB],
      };
      const next = editorReducer(state, { type: "REDO" });
      expect(next.cutList).toEqual(cutListB);
      expect(next.redoStack).toEqual([]);
      expect(next.undoStack).toEqual([cutListA]);
    });

    it("is a no-op when redoStack is empty", () => {
      const cutList = makeCutList([makeSlot(0)]);
      const state = { ...initialState, cutList, undoStack: [], redoStack: [] };
      const next = editorReducer(state, { type: "REDO" });
      expect(next.cutList).toEqual(cutList);
      expect(next.redoStack).toEqual([]);
      expect(next.undoStack).toEqual([]);
    });
  });

  describe("MAX_UNDO_DEPTH", () => {
    it("drops oldest undo after 50 ops", () => {
      let state: import("./useEditor").EditorState = { ...initialState, cutList: makeCutList([makeSlot(0)]) };
      for (let i = 0; i < 51; i++) {
        state = editorReducer(state, { type: "UPDATE_SLOT", index: 0, slot: { subjectHint: `v${i}` } });
      }
      expect(state.undoStack).toHaveLength(50);
      expect(state.undoStack[0].slots[0].subjectHint).toBe("v1");
      expect(state.undoStack[49].slots[0].subjectHint).toBe("v50");
    });
  });

  describe("selection state", () => {
    it("SELECT_SLOT updates selectedSlotIndex and clears selectedOverlayId", () => {
      const state = { ...initialState, selectedOverlayId: "ov1" };
      const next = editorReducer(state, { type: "SELECT_SLOT", index: 3 });
      expect(next.selectedSlotIndex).toBe(3);
      expect(next.selectedOverlayId).toBeNull();
    });

    it("SELECT_OVERLAY updates selectedOverlayId and clears selectedSlotIndex", () => {
      const state = { ...initialState, selectedSlotIndex: 3 };
      const next = editorReducer(state, { type: "SELECT_OVERLAY", id: "ov1" });
      expect(next.selectedOverlayId).toBe("ov1");
      expect(next.selectedSlotIndex).toBeNull();
    });

    it("SET_CURRENT_TIME does not touch undo", () => {
      const cutList = makeCutList([makeSlot(0)]);
      const state = { ...initialState, cutList, undoStack: [cutList] };
      const next = editorReducer(state, { type: "SET_CURRENT_TIME", payload: 12.5 });
      expect(next.currentTime).toBe(12.5);
      expect(next.undoStack).toHaveLength(1);
    });
  });
});
