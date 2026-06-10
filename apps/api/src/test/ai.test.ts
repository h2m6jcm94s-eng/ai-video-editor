import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { applyPromptEdit, transcribeAudio } from "../services/ai";

describe("AI Service", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  describe("applyPromptEdit", () => {
    const mockCutList = {
      globals: {
        totalDurationS: 30,
        tempoBpm: 120,
        timeSignature: "4/4",
        energyCurve: [],
        sectionMarkers: [],
        aspectRatio: "9:16",
      },
      slots: [
        {
          index: 0,
          startS: 0,
          durationS: 5,
          beatIndex: 0,
          section: "intro",
          transitionIn: "hard_cut",
          transitionOut: "hard_cut",
          targetShotType: "wide",
          subjectHint: "establishing shot",
          motionHint: "static",
          energyLevel: 0.5,
          requiredTags: [],
          avoidTags: [],
          effects: [],
        },
      ],
      overlays: [],
      audioTracks: [],
    };

    const makeClaudeResponse = (diff: unknown[], explanation: string, stopReason?: string) => ({
      json: async () => ({
        content: [{ type: "text", text: JSON.stringify({ diff, explanation }) }],
        stop_reason: stopReason,
      }),
      ok: true,
      status: 200,
    });

    const makeOpenAIResponse = (diff: unknown[], explanation: string, finishReason?: string) => ({
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ diff, explanation }) }, finish_reason: finishReason }],
      }),
      ok: true,
      status: 200,
    });

    function withInstantRetries<T>(fn: () => Promise<T>): Promise<T> {
      const original = global.setTimeout;
      global.setTimeout = ((cb: any) => {
        if (typeof cb === "function") cb();
        return 0;
      }) as any;
      return fn().finally(() => {
        global.setTimeout = original;
      });
    }

    it("calls Claude and applies diff", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "replace", path: "/slots/0/transitionIn", value: "fade" }], "Added fade") as any
      );

      const result = await applyPromptEdit({
        userId: "user-1",
        prompt: "fade in the first clip",
        cutList: mockCutList,
      });

      expect(result.diff).toHaveLength(1);
      expect(result.explanation).toBe("Added fade");
      expect((result.newCutList as any).slots[0].transitionIn).toBe("fade");
    });

    it("calls OpenAI when Claude fails and fallback succeeds", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch)
        .mockRejectedValueOnce(new Error("Claude down"))
        .mockResolvedValueOnce(
          makeOpenAIResponse([{ op: "add", path: "/overlays", value: [] }], "Added overlays") as any
        );

      const result = await applyPromptEdit({
        userId: "user-1",
        prompt: "add overlays",
        cutList: mockCutList,
      });

      expect(result.explanation).toBe("Added overlays");
    });

    it("falls back to OpenAI when provider is openai", async () => {
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "openai");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeOpenAIResponse([{ op: "replace", path: "/globals/tempoBpm", value: 140 }], "Speed up") as any
      );

      const result = await applyPromptEdit({
        userId: "user-1",
        prompt: "increase tempo",
        cutList: mockCutList,
      });

      expect((result.newCutList as any).globals.tempoBpm).toBe(140);
    });

    it("falls back to Claude when provider is unknown", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "unknown-provider");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "replace", path: "/globals/tempoBpm", value: 130 }], "Adjusted") as any
      );

      const result = await applyPromptEdit({
        userId: "user-1",
        prompt: "adjust tempo",
        cutList: mockCutList,
      });

      expect((result.newCutList as any).globals.tempoBpm).toBe(130);
    });

    it("applies multiple JSON Patch operations", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse(
          [
            { op: "replace", path: "/slots/0/durationS", value: 3 },
            {
              op: "add",
              path: "/slots/-",
              value: {
                index: 1,
                startS: 3,
                durationS: 2,
                beatIndex: 1,
                section: "verse",
                transitionIn: "hard_cut",
                transitionOut: "hard_cut",
                targetShotType: "medium",
                subjectHint: "subject",
                motionHint: "pan",
                energyLevel: 0.5,
                requiredTags: [],
                avoidTags: [],
                effects: [],
              },
            },
          ],
          "Shortened and added"
        ) as any
      );

      const result = await applyPromptEdit({ userId: "user-1", prompt: "edit", cutList: mockCutList });
      const list = result.newCutList as any;
      expect(list.slots).toHaveLength(2);
      expect(list.slots[0].durationS).toBe(3);
      expect(list.slots[1].index).toBe(1);
    });

    it("handles move operation", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      const listWithSlots = {
        ...mockCutList,
        slots: [
          { ...mockCutList.slots[0], index: 0, startS: 0, durationS: 2 },
          { ...mockCutList.slots[0], index: 1, startS: 2, durationS: 3 },
        ],
      };
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "move", from: "/slots/0", path: "/slots/1" }], "Moved") as any
      );

      const result = await applyPromptEdit({ userId: "user-1", prompt: "move", cutList: listWithSlots });
      expect((result.newCutList as any).slots).toHaveLength(2);
    });

    it("handles copy operation", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "copy", from: "/slots/0", path: "/slots/1" }], "Copied") as any
      );

      const result = await applyPromptEdit({ userId: "user-1", prompt: "copy", cutList: mockCutList });
      expect((result.newCutList as any).slots).toHaveLength(2);
    });

    it("handles remove operation on arrays", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      const listWithSlots = {
        ...mockCutList,
        slots: [
          { ...mockCutList.slots[0], index: 0, startS: 0, durationS: 2 },
          { ...mockCutList.slots[0], index: 1, startS: 2, durationS: 3 },
        ],
      };
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "remove", path: "/slots/0" }], "Removed first") as any
      );

      const result = await applyPromptEdit({ userId: "user-1", prompt: "remove first", cutList: listWithSlots });
      expect((result.newCutList as any).slots).toHaveLength(1);
      expect((result.newCutList as any).slots[0].index).toBe(1);
    });

    it("handles remove operation on nested array path", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      const listWithNested = {
        ...mockCutList,
        slots: [{ ...mockCutList.slots[0], effects: [{ type: "zoom" as const, startS: 0, endS: 1 }] }],
      };
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "remove", path: "/slots/0/effects/0" }], "Removed nested") as any
      );

      const result = await applyPromptEdit({ userId: "user-1", prompt: "remove nested", cutList: listWithNested });
      expect((result.newCutList as any).slots[0].effects).toHaveLength(0);
    });

    it("handles remove operation on objects", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      const listWithOptional = {
        ...mockCutList,
        slots: [{ ...mockCutList.slots[0], selectedClipId: "clip-1" }],
      };
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "remove", path: "/slots/0/selectedClipId" }], "Removed clip") as any
      );

      const result = await applyPromptEdit({ userId: "user-1", prompt: "remove clip", cutList: listWithOptional });
      expect((result.newCutList as any).slots[0]).not.toHaveProperty("selectedClipId");
    });

    it("throws when no API keys are configured", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "");
      vi.stubEnv("OPENAI_API_KEY", "");
      vi.stubEnv("AI_PROVIDER", "claude");

      await expect(
        applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList })
      ).rejects.toThrow("AI prompt edit failed");
    });

    it("returns safe fallback on non-JSON response after retry", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch)
        .mockResolvedValueOnce({
          json: async () => ({ content: [{ type: "text", text: "I changed the fade to dissolve" }] }),
          ok: true,
          status: 200,
        } as any)
        .mockResolvedValueOnce({
          json: async () => ({ choices: [{ message: { content: "Also not JSON" } }] }),
          ok: true,
          status: 200,
        } as any);

      const result = await applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList });
      expect(result.fallback).toBeDefined();
      expect(result.fallback?.reason).toBe("invalid_json");
      expect(result.explanation).toBe("AI returned an unexpected response. No changes applied.");
      expect(result.newCutList).toEqual(mockCutList);
    });

    it("strips markdown fences from response", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce({
        json: async () => ({
          content: [{ type: "text", text: "```json\n{\"diff\":[],\"explanation\":\"ok\"}\n```" }],
        }),
        ok: true,
        status: 200,
      } as any);

      const result = await applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList });
      expect(result.explanation).toBe("ok");
    });

    it("throws on OpenAI 401 with PROVIDER_INVALID_RESPONSE code", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "openai");
      vi.mocked(fetch)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          text: async () => "Unauthorized",
        } as any)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          text: async () => "Unauthorized",
        } as any);

      await expect(
        applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList })
      ).rejects.toThrow("AI prompt edit failed");
    });

    it("retries on Claude 429 and eventually succeeds", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");

      await withInstantRetries(async () => {
        vi.mocked(fetch)
          .mockResolvedValueOnce({ ok: false, status: 429, text: async () => "Rate limited" } as any)
          .mockResolvedValueOnce(
            makeClaudeResponse([{ op: "replace", path: "/slots/0/transitionIn", value: "fade" }], "Added fade") as any
          );

        const result = await applyPromptEdit({ userId: "user-1", prompt: "fade", cutList: mockCutList });
        expect(result.explanation).toBe("Added fade");
        expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
      });
    });

    it("retries on Claude 429 and falls back to OpenAI after exhaustion", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "claude");

      await withInstantRetries(async () => {
        vi.mocked(fetch)
          .mockResolvedValueOnce({ ok: false, status: 429, text: async () => "Rate limited" } as any)
          .mockResolvedValueOnce({ ok: false, status: 429, text: async () => "Rate limited" } as any)
          .mockResolvedValueOnce({ ok: false, status: 429, text: async () => "Rate limited" } as any)
          .mockResolvedValueOnce({ ok: false, status: 429, text: async () => "Rate limited" } as any)
          .mockResolvedValueOnce(
            makeOpenAIResponse([{ op: "replace", path: "/slots/0/transitionIn", value: "dissolve" }], "Dissolved") as any
          );

        const result = await applyPromptEdit({ userId: "user-1", prompt: "dissolve", cutList: mockCutList });
        expect(result.explanation).toBe("Dissolved");
        expect(vi.mocked(fetch)).toHaveBeenCalledTimes(5);
      });
    });

    it("throws PROVIDER_RATE_LIMITED when both providers exhaust retries", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "claude");

      await withInstantRetries(async () => {
        const rateLimited = { ok: false, status: 429, text: async () => "Rate limited" };
        vi.mocked(fetch)
          .mockResolvedValueOnce(rateLimited as any)
          .mockResolvedValueOnce(rateLimited as any)
          .mockResolvedValueOnce(rateLimited as any)
          .mockResolvedValueOnce(rateLimited as any)
          .mockResolvedValueOnce(rateLimited as any)
          .mockResolvedValueOnce(rateLimited as any)
          .mockResolvedValueOnce(rateLimited as any)
          .mockResolvedValueOnce(rateLimited as any);

        await expect(
          applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList })
        ).rejects.toThrow("AI prompt edit failed");
        expect(vi.mocked(fetch)).toHaveBeenCalledTimes(8);
      });
    });

    it("returns safe fallback when Claude returns stop_reason refusal", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce({
        json: async () => ({
          content: [{ type: "text", text: "I cannot help with that." }],
          stop_reason: "refusal",
        }),
        ok: true,
        status: 200,
      } as any);

      const result = await applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList });
      expect(result.fallback).toBeDefined();
      expect(result.fallback?.reason).toBe("blocked");
      expect(result.explanation).toBe("AI declined to respond due to safety policies. No changes applied.");
      expect(result.newCutList).toEqual(mockCutList);
    });

    it("returns safe fallback when OpenAI returns finish_reason content_filter", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "openai");
      vi.mocked(fetch).mockResolvedValueOnce({
        json: async () => ({
          choices: [{ message: { content: "" }, finish_reason: "content_filter" }],
        }),
        ok: true,
        status: 200,
      } as any);

      const result = await applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList });
      expect(result.fallback).toBeDefined();
      expect(result.fallback?.reason).toBe("content_filter");
      expect(result.explanation).toBe("AI response was blocked by content filters. No changes applied.");
      expect(result.newCutList).toEqual(mockCutList);
    });

    it("returns safe fallback when both providers refuse", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch)
        .mockResolvedValueOnce({
          json: async () => ({
            content: [{ type: "text", text: "I cannot help with that." }],
            stop_reason: "refusal",
          }),
          ok: true,
          status: 200,
        } as any)
        .mockResolvedValueOnce({
          json: async () => ({
            choices: [{ message: { content: "" }, finish_reason: "content_filter" }],
          }),
          ok: true,
          status: 200,
        } as any);

      const result = await applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList });
      expect(result.fallback).toBeDefined();
      expect(result.fallback?.reason).toBe("blocked");
      expect(result.newCutList).toEqual(mockCutList);
    });

    it("throws CUTLIST_SCHEMA_DRIFT when patched cut list is invalid", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse(
          [
            {
              op: "add",
              path: "/slots/-",
              value: { index: 1, startS: 5 }, // missing required fields
            },
          ],
          "Added slot"
        ) as any
      );

      try {
        await applyPromptEdit({ userId: "user-1", prompt: "add slot", cutList: mockCutList });
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.code).toBe("CUTLIST_SCHEMA_DRIFT");
      }
    });

    it("throws CUTLIST_SCHEMA_DRIFT when patched cut list has extra fields", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "add", path: "/evil", value: true }], "Added evil") as any
      );

      try {
        await applyPromptEdit({ userId: "user-1", prompt: "test", cutList: mockCutList });
        expect.fail("Should have thrown");
      } catch (err: any) {
        expect(err.code).toBe("CUTLIST_SCHEMA_DRIFT");
      }
    });
  });

  describe("transcribeAudio", () => {
    it("calls Whisper API and returns segments", async () => {
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.mocked(fetch).mockResolvedValueOnce({
        json: async () => ({
          segments: [
            { text: "Hello world", start: 0, end: 2 },
            { text: "Second line", start: 2.5, end: 5 },
          ],
        }),
        ok: true,
        status: 200,
      } as any);

      const result = await transcribeAudio("user-1", Buffer.from("audio"), "test.mp3");
      expect(result).toHaveLength(2);
      expect(result[0].text).toBe("Hello world");
      expect(result[0].start).toBe(0);
    });

    it("returns single segment when no segments array", async () => {
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.mocked(fetch).mockResolvedValueOnce({
        json: async () => ({ text: "Only text" }),
        ok: true,
        status: 200,
      } as any);

      const result = await transcribeAudio("user-1", Buffer.from("audio"), "test.mp3");
      expect(result).toHaveLength(1);
      expect(result[0].text).toBe("Only text");
    });

    it("throws on API error", async () => {
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 429,
        text: async () => "Rate limited",
      } as any);

      await expect(transcribeAudio("user-1", Buffer.from("audio"), "test.mp3")).rejects.toThrow("Whisper API error");
    });

    it("throws when OPENAI_API_KEY is missing", async () => {
      vi.stubEnv("OPENAI_API_KEY", "");
      await expect(transcribeAudio("user-1", Buffer.from("audio"), "test.mp3")).rejects.toThrow("not configured");
    });
  });
});
