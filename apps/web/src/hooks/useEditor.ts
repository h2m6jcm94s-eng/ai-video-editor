// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useReducer, useCallback } from "react";
import type { CutList, Slot, Overlay, Asset } from "@/types/api";

interface EditorState {
  cutList: CutList | null;
  selectedSlotIndex: number | null;
  selectedOverlayId: string | null;
  isPlaying: boolean;
  currentTime: number;
  zoomLevel: number;
  assets: Asset[];
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
  | { type: "SELECT_SLOT"; index: number | null }
  | { type: "SELECT_OVERLAY"; id: string | null }
  | { type: "SET_PLAYING"; payload: boolean }
  | { type: "SET_CURRENT_TIME"; payload: number }
  | { type: "SET_ZOOM"; payload: number }
  | { type: "SET_ASSETS"; payload: Asset[] };

function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "SET_CUTLIST":
      return { ...state, cutList: action.payload };
    case "UPDATE_SLOT": {
      if (!state.cutList) return state;
      const slots = [...state.cutList.slots];
      slots[action.index] = { ...slots[action.index], ...action.slot };
      return { ...state, cutList: { ...state.cutList, slots } };
    }
    case "ADD_SLOT": {
      if (!state.cutList) return state;
      return {
        ...state,
        cutList: { ...state.cutList, slots: [...state.cutList.slots, action.slot] },
      };
    }
    case "REMOVE_SLOT": {
      if (!state.cutList) return state;
      const removed = state.cutList.slots[action.index];
      const slots = state.cutList.slots.filter((_, i) => i !== action.index);
      if (action.ripple && removed) {
        const removedEnd = removed.start_s + removed.duration_s;
        for (let i = action.index; i < slots.length; i++) {
          if (slots[i].start_s >= removedEnd) {
            slots[i] = { ...slots[i], start_s: slots[i].start_s - removed.duration_s };
          }
        }
      }
      return { ...state, cutList: { ...state.cutList, slots } };
    }
    case "REORDER_SLOTS": {
      if (!state.cutList) return state;
      return { ...state, cutList: { ...state.cutList, slots: action.slots } };
    }
    case "ADD_OVERLAY": {
      if (!state.cutList) return state;
      return {
        ...state,
        cutList: { ...state.cutList, overlays: [...state.cutList.overlays, action.overlay] },
      };
    }
    case "UPDATE_OVERLAY": {
      if (!state.cutList) return state;
      const overlays = state.cutList.overlays.map((o) =>
        o.id === action.id ? { ...o, ...action.overlay } : o
      );
      return { ...state, cutList: { ...state.cutList, overlays } };
    }
    case "REMOVE_OVERLAY": {
      if (!state.cutList) return state;
      return {
        ...state,
        cutList: {
          ...state.cutList,
          overlays: state.cutList.overlays.filter((o) => o.id !== action.id),
        },
      };
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
    ...initial,
  });

  const setCutList = useCallback((cutList: CutList) => dispatch({ type: "SET_CUTLIST", payload: cutList }), []);
  const updateSlot = useCallback((index: number, slot: Partial<Slot>) => dispatch({ type: "UPDATE_SLOT", index, slot }), []);
  const addSlot = useCallback((slot: Slot) => dispatch({ type: "ADD_SLOT", slot }), []);
  const removeSlot = useCallback((index: number, ripple?: boolean) => dispatch({ type: "REMOVE_SLOT", index, ripple }), []);
  const reorderSlots = useCallback((slots: Slot[]) => dispatch({ type: "REORDER_SLOTS", slots }), []);
  const addOverlay = useCallback((overlay: Overlay) => dispatch({ type: "ADD_OVERLAY", overlay }), []);
  const updateOverlay = useCallback((id: string, overlay: Partial<Overlay>) => dispatch({ type: "UPDATE_OVERLAY", id, overlay }), []);
  const removeOverlay = useCallback((id: string) => dispatch({ type: "REMOVE_OVERLAY", id }), []);
  const selectSlot = useCallback((index: number | null) => dispatch({ type: "SELECT_SLOT", index }), []);
  const selectOverlay = useCallback((id: string | null) => dispatch({ type: "SELECT_OVERLAY", id }), []);
  const setPlaying = useCallback((payload: boolean) => dispatch({ type: "SET_PLAYING", payload }), []);
  const setCurrentTime = useCallback((payload: number) => dispatch({ type: "SET_CURRENT_TIME", payload }), []);
  const setZoom = useCallback((payload: number) => dispatch({ type: "SET_ZOOM", payload }), []);
  const setAssets = useCallback((payload: Asset[]) => dispatch({ type: "SET_ASSETS", payload }), []);

  return {
    state,
    actions: {
      setCutList,
      updateSlot,
      addSlot,
      removeSlot,
      reorderSlots,
      addOverlay,
      updateOverlay,
      removeOverlay,
      selectSlot,
      selectOverlay,
      setPlaying,
      setCurrentTime,
      setZoom,
      setAssets,
    },
  };
}
