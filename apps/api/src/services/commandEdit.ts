import type { CutList, ParsedCommand, Slot } from "@ai-video-editor/shared-types";
import { randomUUID } from "crypto";
import { applyJsonPatch } from "./ai";

export interface CommandEditResult {
  diff: unknown[];
  explanation: string;
  newCutList: CutList;
  verb?: string;
  fallbackToLLM: boolean;
}

function getSlot(cutList: CutList, slotIndex: number): Slot | undefined {
  return cutList.slots?.[slotIndex];
}

function slotDuration(cutList: CutList, slotIndex: number): number {
  return getSlot(cutList, slotIndex)?.durationS ?? 1;
}

function effectDefaults(effectType: string, durationS: number) {
  const base = {
    id: randomUUID(),
    startS: 0,
    durationS,
  };
  switch (effectType) {
    case "zoom_punch_in":
      return { ...base, type: "zoom_punch_in", params: { targetScale: 1.3, durationMs: 300 } };
    case "shake":
      return { ...base, type: "shake", params: { intensity: 5, durationMs: 300 } };
    case "glitch":
      return { ...base, type: "glitch", params: { intensity: 0.3, durationMs: 200 } };
    case "vignette":
      return { ...base, type: "vignette", params: { intensity: 0.4 } };
    case "film_grain":
      return { ...base, type: "film_grain", params: { intensity: 0.2 } };
    case "color_pop":
      return { ...base, type: "color_pop", params: { saturation: 1.5, hueShift: 0 } };
    case "chromatic_aberration":
      return { ...base, type: "chromatic_aberration", params: { shiftX: 3, shiftY: 0, intensity: 0.3 } };
    case "camera_motion":
      return { ...base, type: "camera_motion", params: { motion: "zoom_in", intensity: 0.3 } };
    default:
      return { ...base, type: effectType, params: {} };
  }
}

export function applyCommand(command: ParsedCommand, cutList: CutList): CommandEditResult {
  const diff: unknown[] = [];
  let explanation = "";

  switch (command.verb) {
    case "trim_slot": {
      const { slotIndex, durationS } = command.params as {
        slotIndex: number;
        durationS?: number;
      };
      if (durationS !== undefined) {
        diff.push({
          op: "replace",
          path: `/slots/${slotIndex}/durationS`,
          value: durationS,
        });
        explanation = `Trimmed slot ${slotIndex} to ${durationS}s.`;
      } else {
        explanation = `Matched trim verb for slot ${slotIndex}, but no duration was specified.`;
      }
      break;
    }

    case "zoom_in":
    case "add_effect": {
      const params = command.params as { slotIndex: number; effectType?: string };
      const effectType =
        command.verb === "zoom_in" ? "zoom_punch_in" : (params.effectType ?? "zoom_punch_in");
      const durationS = slotDuration(cutList, params.slotIndex);
      diff.push({
        op: "add",
        path: `/slots/${params.slotIndex}/effects/-`,
        value: effectDefaults(effectType, durationS),
      });
      explanation = `Added ${effectType} effect to slot ${params.slotIndex}.`;
      break;
    }

    case "apply_filter": {
      const params = command.params as { slotIndex: number; effectType: string };
      const durationS = slotDuration(cutList, params.slotIndex);
      diff.push({
        op: "add",
        path: `/slots/${params.slotIndex}/effects/-`,
        value: effectDefaults(params.effectType, durationS),
      });
      explanation = `Applied ${params.effectType} filter to slot ${params.slotIndex}.`;
      break;
    }

    case "add_text_overlay": {
      const { text, startS, durationS, position } = command.params as {
        text: string;
        startS: number;
        durationS: number;
        position?: string;
      };
      diff.push({
        op: "add",
        path: "/overlays/-",
        value: {
          id: randomUUID(),
          text,
          startS,
          durationS,
          position: position ?? "center",
          font: "Montserrat",
          fontSizePx: 48,
          color: "#FFFFFF",
          stroke: "#000000",
          animation: "pop",
        },
      });
      explanation = `Added text overlay "${text}".`;
      break;
    }

    case "set_transition": {
      const { slotIndex, transition } = command.params as {
        slotIndex?: number;
        transition: string;
      };
      if (slotIndex !== undefined) {
        diff.push({
          op: "replace",
          path: `/slots/${slotIndex}/transitionOut`,
          value: transition,
        });
        explanation = `Set transition for slot ${slotIndex} to ${transition}.`;
      } else {
        diff.push({
          op: "replace",
          path: "/globals/defaultTransition",
          value: transition,
        });
        explanation = `Set default transition to ${transition}.`;
      }
      break;
    }

    case "change_tempo": {
      const { direction } = command.params as { direction: string };
      explanation = `Tempo change (${direction}) is not yet implemented as a deterministic edit.`;
      break;
    }

    default:
      explanation = `Deterministic handler for ${command.verb} is not yet implemented.`;
  }

  const newCutList = applyJsonPatch(cutList, diff) as CutList;
  return {
    diff,
    explanation,
    newCutList,
    verb: command.verb,
    fallbackToLLM: false,
  };
}
