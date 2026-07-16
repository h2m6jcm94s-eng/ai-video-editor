import type { CutList } from "@ai-video-editor/shared-types";
import { describe, expect, it } from "vitest";
import { listVerbs, parseCommand } from "./commandParser";

const emptyCutList: CutList = {
  slots: [],
  globals: {
    totalDurationS: 0,
    tempoBpm: 120,
    timeSignature: "4/4",
    energyCurve: [],
    sectionMarkers: [],
    aspectRatio: "9:16",
  },
  overlays: [],
  audioTracks: [],
  subtitles: [],
};

describe("commandParser", () => {
  it("lists verbs", () => {
    const verbs = listVerbs();
    expect(verbs).toContain("trim_slot");
    expect(verbs).toContain("zoom_in");
  });

  it("parses trim slot 0 to 3 seconds", () => {
    const cmd = parseCommand("trim slot 0 to 3 seconds", emptyCutList);
    expect(cmd).not.toBeNull();
    expect(cmd?.verb).toBe("trim_slot");
    expect(cmd?.params.slotIndex).toBe(0);
    expect(cmd?.params.durationS).toBe(3);
  });

  it("parses zoom in on the first clip", () => {
    const cmd = parseCommand("zoom in on the first clip", {
      ...emptyCutList,
      slots: [{ durationS: 2 } as any],
    });
    expect(cmd?.verb).toBe("zoom_in");
    expect(cmd?.params.slotIndex).toBe(0);
  });

  it("parses apply film grain filter to slot 2", () => {
    const cmd = parseCommand("apply film grain filter to slot 2", emptyCutList);
    expect(cmd?.verb).toBe("apply_filter");
    expect(cmd?.params.effectType).toBe("film_grain");
    expect(cmd?.params.slotIndex).toBe(2);
  });

  it("parses add text overlay", () => {
    const cmd = parseCommand('add text "Hello world"', emptyCutList);
    expect(cmd?.verb).toBe("add_text_overlay");
    expect(cmd?.params.text).toBe("Hello world");
  });

  it("parses set transition to fade", () => {
    const cmd = parseCommand("set transition to fade", emptyCutList);
    expect(cmd?.verb).toBe("set_transition");
    expect(cmd?.params.transition).toBe("fade");
  });

  it("parses speed up", () => {
    const cmd = parseCommand("speed up the video", emptyCutList);
    expect(cmd?.verb).toBe("change_tempo");
    expect(cmd?.params.direction).toBe("faster");
  });

  it("returns null for unrecognized prompts", () => {
    expect(parseCommand("make it feel more cinematic", emptyCutList)).toBeNull();
  });
});
