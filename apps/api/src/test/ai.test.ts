import { describe, it, expect, vi, beforeEach } from "vitest";
import { applyPromptEdit, transcribeAudio } from "../services/ai";

describe("AI Service", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.clearAllMocks();
  });

  describe("applyPromptEdit", () => {
    const mockCutList = {
      globals: { total_duration_s: 30, tempo_bpm: 120 },
      slots: [{ index: 0, start_s: 0, duration_s: 5, transition_in: "hard_cut" }],
    };

    const makeClaudeResponse = (diff: unknown[], explanation: string) => ({
      json: async () => ({
        content: [{ type: "text", text: JSON.stringify({ diff, explanation }) }],
      }),
      ok: true,
      status: 200,
    });

    const makeOpenAIResponse = (diff: unknown[], explanation: string) => ({
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ diff, explanation }) } }],
      }),
      ok: true,
      status: 200,
    });

    beforeEach(() => {
      vi.unstubAllEnvs();
    });

    it("calls Claude and applies diff", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "replace", path: "/slots/0/transition_in", value: "fade" }], "Added fade") as any
      );

      const result = await applyPromptEdit({
        prompt: "fade in the first clip",
        cutList: mockCutList,
      });

      expect(result.diff).toHaveLength(1);
      expect(result.explanation).toBe("Added fade");
      expect((result.newCutList as any).slots[0].transition_in).toBe("fade");
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
        prompt: "add overlays",
        cutList: mockCutList,
      });

      expect(result.explanation).toBe("Added overlays");
    });

    it("falls back to OpenAI when provider is openai", async () => {
      vi.stubEnv("OPENAI_API_KEY", "sk-openai-test");
      vi.stubEnv("AI_PROVIDER", "openai");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeOpenAIResponse([{ op: "replace", path: "/globals/tempo_bpm", value: 140 }], "Speed up") as any
      );

      const result = await applyPromptEdit({
        prompt: "increase tempo",
        cutList: mockCutList,
      });

      expect((result.newCutList as any).globals.tempo_bpm).toBe(140);
    });

    it("applies multiple JSON Patch operations", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse(
          [
            { op: "replace", path: "/slots/0/duration_s", value: 3 },
            { op: "add", path: "/slots/-", value: { index: 1, start_s: 3, duration_s: 2 } },
          ],
          "Shortened and added"
        ) as any
      );

      const result = await applyPromptEdit({ prompt: "edit", cutList: mockCutList });
      const list = result.newCutList as any;
      expect(list.slots).toHaveLength(2);
      expect(list.slots[0].duration_s).toBe(3);
      expect(list.slots[1].index).toBe(1);
    });

    it("handles move operation", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      const listWithSlots = {
        ...mockCutList,
        slots: [
          { index: 0, start_s: 0, duration_s: 2 },
          { index: 1, start_s: 2, duration_s: 3 },
        ],
      };
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "move", from: "/slots/0", path: "/slots/1" }], "Moved") as any
      );

      const result = await applyPromptEdit({ prompt: "move", cutList: listWithSlots });
      expect((result.newCutList as any).slots).toHaveLength(2);
    });

    it("handles copy operation", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce(
        makeClaudeResponse([{ op: "copy", from: "/slots/0", path: "/slots/1" }], "Copied") as any
      );

      const result = await applyPromptEdit({ prompt: "copy", cutList: mockCutList });
      expect((result.newCutList as any).slots).toHaveLength(2);
    });

    it("throws when no API keys are configured", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "");
      vi.stubEnv("OPENAI_API_KEY", "");
      vi.stubEnv("AI_PROVIDER", "claude");

      await expect(
        applyPromptEdit({ prompt: "test", cutList: mockCutList })
      ).rejects.toThrow("AI prompt edit failed");
    });

    it("handles non-JSON response gracefully", async () => {
      vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
      vi.stubEnv("AI_PROVIDER", "claude");
      vi.mocked(fetch).mockResolvedValueOnce({
        json: async () => ({ content: [{ type: "text", text: "I changed the fade to dissolve" }] }),
        ok: true,
        status: 200,
      } as any);

      const result = await applyPromptEdit({ prompt: "test", cutList: mockCutList });
      expect(result.diff).toEqual([]);
      expect(result.explanation).toContain("changed the fade");
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

      const result = await applyPromptEdit({ prompt: "test", cutList: mockCutList });
      expect(result.explanation).toBe("ok");
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

      const result = await transcribeAudio(Buffer.from("audio"), "test.mp3");
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

      const result = await transcribeAudio(Buffer.from("audio"), "test.mp3");
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

      await expect(transcribeAudio(Buffer.from("audio"), "test.mp3")).rejects.toThrow("Whisper API error");
    });

    it("throws when OPENAI_API_KEY is missing", async () => {
      vi.stubEnv("OPENAI_API_KEY", "");
      await expect(transcribeAudio(Buffer.from("audio"), "test.mp3")).rejects.toThrow("not configured");
    });
  });
});
