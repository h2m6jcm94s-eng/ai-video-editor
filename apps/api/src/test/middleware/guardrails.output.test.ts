import { beforeEach, describe, expect, it, vi } from "vitest";
import { validateAIResponse } from "../../middleware/guardrails";

describe("validateAIResponse", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.clearAllMocks();
  });

  it("returns allowed=true when guardrails service approves", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ allowed: true }),
    } as any);

    const result = await validateAIResponse('{"diff":[],"explanation":"ok"}');
    expect(result.allowed).toBe(true);
  });

  it("returns allowed=false when response contains secrets", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        allowed: false,
        reason: "Output blocked by guardrails: secrets",
        flagged_categories: ["secrets"],
        confidence: 0.95,
      }),
    } as any);

    const result = await validateAIResponse("Here is your key: sk-ant-api03-XXX");
    expect(result.allowed).toBe(false);
    expect(result.flagged_categories).toContain("secrets");
  });

  it("returns allowed=false when response is toxic", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        allowed: false,
        reason: "Output blocked by guardrails: toxicity",
        flagged_categories: ["toxicity"],
        confidence: 0.88,
      }),
    } as any);

    const result = await validateAIResponse("You are the worst person ever");
    expect(result.allowed).toBe(false);
    expect(result.flagged_categories).toContain("toxicity");
  });

  it("returns allowed=true for normal cut-list JSON", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ allowed: true }),
    } as any);

    const normalCutList = JSON.stringify({
      globals: { totalDurationS: 30, tempoBpm: 120 },
      slots: [{ index: 0, startS: 0, durationS: 5, beatIndex: 0, section: "intro" }],
    });
    const result = await validateAIResponse(normalCutList);
    expect(result.allowed).toBe(true);
  });

  it("fails open on 5xx from guardrails service", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 503,
    } as any);

    const result = await validateAIResponse("any text");
    expect(result.allowed).toBe(true);
  });

  it("fails open on network timeout", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("Network error"));

    const result = await validateAIResponse("any text");
    expect(result.allowed).toBe(true);
  });

  it("calls /evaluate/output endpoint", async () => {
    vi.stubEnv("GUARDRAILS_URL", "http://guardrails:8000");
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ allowed: true }),
    } as any);

    await validateAIResponse("test");
    const call = vi.mocked(fetch).mock.calls[0];
    expect(call[0]).toBe("http://guardrails:8000/evaluate/output");
    expect(call[1]).toMatchObject({ method: "POST" });
    expect(JSON.parse((call[1] as any).body)).toEqual({ text: "test" });
  });
});
