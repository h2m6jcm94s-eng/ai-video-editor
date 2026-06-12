// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useCallback, useMemo, useReducer } from "react";
import type { Asset, AudioTrack, CutList, Effect, Overlay, Slot } from "@/types/api";

const MAX_UNDO_DEPTH = 50;

export interface EditorState {
  cutList: CutList | null;
  selectedSlotIndex: number | null;
  selectedOverlayId: string | null;
  isPlaying: boolean;
  currentTime: number;
  zoomLevel: number;
  assets: Asset[];
  undoStack: CutList[];
  redoStack: CutList[];
}

function pushUndo(state: EditorState): EditorState {
  if (!state.cutList) return state;
  const nextUndo = [...state.undoStack, state.cutList];
  if (nextUndo.length > MAX_UNDO_DEPTH) nextUndo.shift();
  return { ...state, undoStack: nextUndo, redoStack: [] };
}

type EditorAction =
  | { type: "SET_CUTLIST"; payload: CutList }
  | { type: "UPDATE_SLOT"; index: number; slot: Partial<Slot> }
  | { type: "ADD_SLOT"; slot: Slot }
  | { type: "REMOVE_SLOT"; index: number; ripple?: boolean }
  | { type: "REORDER_SLOTS"; slots: Slot[] }
  | { type: "ADD_OVERLAY"; overlay: Overlay }
  | { type: "UPDATE_OVERLAY"; id: string; overlay: Partial<Overlay> }
  | { type: "REMOVE_OVERLAY"; id: string }
  | { type: "ADD_EFFECT"; slotIndex: number; effect: Effect }
  | { type: "REMOVE_EFFECT"; slotIndex: number; effectId: string }
  | { type: "ADD_AUDIO_TRACK"; track: AudioTrack }
  | { type: "REMOVE_AUDIO_TRACK"; index: number }
  | { type: "SELECT_SLOT"; index: number | null }
  | { type: "SELECT_OVERLAY"; id: string | null }
  | { type: "SET_PLAYING"; payload: boolean }
  | { type: "SET_CURRENT_TIME"; payload: number }
  | { type: "SET_ZOOM"; payload: number }
  | { type: "SET_ASSETS"; payload: Asset[] }
  | { type: "PROMPT_APPLY"; cutList: CutList }
  | { type: "UNDO" }
  | { type: "REDO" };

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "SET_CUTLIST":
      return { ...state, cutList: action.payload };
    case "UPDATE_SLOT": {
      if (!state.cutList) return state;
      const slots = [...state.cutList.slots];
      slots[action.index] = { ...slots[action.index], ...action.slot };
      return pushUndo({ ...state, cutList: { ...state.cutList, slots } });
    }
    case "ADD_SLOT": {
      if (!state.cutList) return state;
      return pushUndo({
        ...state,
        cutList: { ...state.cutList, slots: [...state.cutList.slots, action.slot] },
      });
    }
    case "REMOVE_SLOT": {
      if (!state.cutList) return state;
      const removed = state.cutList.slots[action.index];
      const slots = state.cutList.slots.filter((_, i) => i !== action.index);
      if (action.ripple && removed) {
        const removedEnd = removed.startS + removed.durationS;
        for (let i = action.index; i < slots.length; i++) {
          if (slots[i].startS >= removedEnd) {
            slots[i] = { ...slots[i], startS: slots[i].startS - removed.durationS };
          }
        }
      }
      return pushUndo({ ...state, cutList: { ...state.cutList, slots } });
    }
    case "REORDER_SLOTS": {
      if (!state.cutList) return state;
      return pushUndo({ ...state, cutList: { ...state.cutList, slots: action.slots } });
    }
    case "ADD_OVERLAY": {
      if (!state.cutList) return state;
      return pushUndo({
        ...state,
        cutList: { ...state.cutList, overlays: [...state.cutList.overlays, action.overlay] },
      });
    }
    case "UPDATE_OVERLAY": {
      if (!state.cutList) return state;
      const overlays = state.cutList.overlays.map((o) =>
        o.id === action.id ? { ...o, ...action.overlay } : o,
      );
      return pushUndo({ ...state, cutList: { ...state.cutList, overlays } });
    }
    case "REMOVE_OVERLAY": {
      if (!state.cutList) return state;
      return pushUndo({
        ...state,
        cutList: {
          ...state.cutList,
          overlays: state.cutList.overlays.filter((o) => o.id !== action.id),
        },
      });
    }
    case "ADD_EFFECT": {
      if (!state.cutList) return state;
      const effectSlots = [...state.cutList.slots];
      const slot = effectSlots[action.slotIndex];
      if (!slot) return state;
      effectSlots[action.slotIndex] = {
        ...slot,
        effects: [...(slot.effects || []), action.effect],
      };
      return pushUndo({ ...state, cutList: { ...state.cutList, slots: effectSlots } });
    }
    case "REMOVE_EFFECT": {
      if (!state.cutList) return state;
      const effectSlots = [...state.cutList.slots];
      const slot = effectSlots[action.slotIndex];
      if (!slot) return state;
      effectSlots[action.slotIndex] = {
        ...slot,
        effects: (slot.effects || []).filter((e) => e.id !== action.effectId),
      };
      return pushUndo({ ...state, cutList: { ...state.cutList, slots: effectSlots } });
    }
    case "ADD_AUDIO_TRACK": {
      if (!state.cutList) return state;
      return pushUndo({
        ...state,
        cutList: {
          ...state.cutList,
          audioTracks: [...(state.cutList.audioTracks || []), action.track],
        },
      });
    }
    case "REMOVE_AUDIO_TRACK": {
      if (!state.cutList) return state;
      return pushUndo({
        ...state,
        cutList: {
          ...state.cutList,
          audioTracks: (state.cutList.audioTracks || []).filter((_, i) => i !== action.index),
        },
      });
    }
    case "SELECT_SLOT":
      return { ...state, selectedSlotIndex: action.index, selectedOverlayId: null };
    case "SELECT_OVERLAY":
      return { ...state, selectedOverlayId: action.id, selectedSlotIndex: null };
    case "SET_PLAYING":
      return { ...state, isPlaying: action.payload };
    case "SET_CURRENT_TIME":
      return { ...state, currentTime: action.payload };
    case "SET_ZOOM":
      return { ...state, zoomLevel: action.payload };
    case "SET_ASSETS":
      return { ...state, assets: action.payload };
    case "PROMPT_APPLY": {
      if (!state.cutList) return state;
      return {
        ...state,
        cutList: action.cutList,
        undoStack: [...state.undoStack, state.cutList],
        redoStack: [],
      };
    }
    case "UNDO": {
      const prev = state.undoStack[state.undoStack.length - 1];
      if (!prev || !state.cutList) return state;
      return {
        ...state,
        cutList: prev,
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, state.cutList],
      };
    }
    case "REDO": {
      const next = state.redoStack[state.redoStack.length - 1];
      if (!next) return state;
      return {
        ...state,
        cutList: next,
        redoStack: state.redoStack.slice(0, -1),
        undoStack: [...state.undoStack, state.cutList!],
      };
    }
    default:
      return state;
  }
}

export function useEditor(initial: Partial<EditorState> = {}) {
  const [state, dispatch] = useReducer(editorReducer, {
    cutList: null,
    selectedSlotIndex: null,
    selectedOverlayId: null,
    isPlaying: false,
    currentTime: 0,
    zoomLevel: 1,
    assets: [],
    undoStack: [],
    redoStack: [],
    ...initial,
  });

  const setCutList = useCallback(
    (cutList: CutList) => dispatch({ type: "SET_CUTLIST", payload: cutList }),
    [],
  );
  const updateSlot = useCallback(
    (index: number, slot: Partial<Slot>) => dispatch({ type: "UPDATE_SLOT", index, slot }),
    [],
  );
  const addSlot = useCallback((slot: Slot) => dispatch({ type: "ADD_SLOT", slot }), []);
  const removeSlot = useCallback(
    (index: number, ripple?: boolean) => dispatch({ type: "REMOVE_SLOT", index, ripple }),
    [],
  );
  const reorderSlots = useCallback((slots: Slot[]) => dispatch({ type: "REORDER_SLOTS", slots }), []);
  const addOverlay = useCallback((overlay: Overlay) => dispatch({ type: "ADD_OVERLAY", overlay }), []);
  const updateOverlay = useCallback(
    (id: string, overlay: Partial<Overlay>) => dispatch({ type: "UPDATE_OVERLAY", id, overlay }),
    [],
  );
  const removeOverlay = useCallback((id: string) => dispatch({ type: "REMOVE_OVERLAY", id }), []);
  const addEffect = useCallback(
    (slotIndex: number, effect: Effect) => dispatch({ type: "ADD_EFFECT", slotIndex, effect }),
    [],
  );
  const removeEffect = useCallback(
    (slotIndex: number, effectId: string) => dispatch({ type: "REMOVE_EFFECT", slotIndex, effectId }),
    [],
  );
  const addAudioTrack = useCallback((track: AudioTrack) => dispatch({ type: "ADD_AUDIO_TRACK", track }), []);
  const removeAudioTrack = useCallback(
    (index: number) => dispatch({ type: "REMOVE_AUDIO_TRACK", index }),
    [],
  );
  const selectSlot = useCallback((index: number | null) => dispatch({ type: "SELECT_SLOT", index }), []);
  const selectOverlay = useCallback((id: string | null) => dispatch({ type: "SELECT_OVERLAY", id }), []);
  const setPlaying = useCallback((payload: boolean) => dispatch({ type: "SET_PLAYING", payload }), []);
  const setCurrentTime = useCallback(
    (payload: number) => dispatch({ type: "SET_CURRENT_TIME", payload }),
    [],
  );
  const setZoom = useCallback((payload: number) => dispatch({ type: "SET_ZOOM", payload }), []);
  const setAssets = useCallback((payload: Asset[]) => dispatch({ type: "SET_ASSETS", payload }), []);
  const promptApply = useCallback((cutList: CutList) => dispatch({ type: "PROMPT_APPLY", cutList }), []);
  const undo = useCallback(() => dispatch({ type: "UNDO" }), []);
  const redo = useCallback(() => dispatch({ type: "REDO" }), []);

  const actions = useMemo(
    () => ({
      setCutList,
      updateSlot,
      addSlot,
      removeSlot,
      reorderSlots,
      addOverlay,
      updateOverlay,
      removeOverlay,
      addEffect,
      removeEffect,
      addAudioTrack,
      removeAudioTrack,
      selectSlot,
      selectOverlay,
      setPlaying,
      setCurrentTime,
      setZoom,
      setAssets,
      promptApply,
      undo,
      redo,
    }),
    [
      setCutList,
      updateSlot,
      addSlot,
      removeSlot,
      reorderSlots,
      addOverlay,
      updateOverlay,
      removeOverlay,
      addEffect,
      removeEffect,
      addAudioTrack,
      removeAudioTrack,
      selectSlot,
      selectOverlay,
      setPlaying,
      setCurrentTime,
      setZoom,
      setAssets,
      promptApply,
      undo,
      redo,
    ],
  );

  return {
    state,
    actions,
  };
}
