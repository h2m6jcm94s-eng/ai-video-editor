import { API_ERROR_CODES } from "@ai-video-editor/shared-types";
import { describe, expect, it } from "vitest";
import { APIError } from "./error";

const DEFAULT_MESSAGE = "Something went wrong.";

// Codes that intentionally map to the generic fallback
const EXPECTED_DEFAULT_CODES = new Set([
  "INTERNAL_ERROR",
  "USER_RESOLUTION_ERROR",
  "TEMPORAL_ERROR",
  "GUARDRAILS_VIOLATION",
  "MISSING_ASSETS",
  "BUDGET_EXCEEDED",
]);

describe("APIError.userMessage", () => {
  it("maps every known error code to a non-default message", () => {
    for (const code of API_ERROR_CODES) {
      const err = new APIError(500, code, "server msg");
      if (EXPECTED_DEFAULT_CODES.has(code)) {
        expect(err.userMessage, `code ${code}`).toBe(DEFAULT_MESSAGE);
      } else {
        expect(err.userMessage, `code ${code}`).not.toBe(DEFAULT_MESSAGE);
      }
    }
  });

  it("returns actionable messages for specific codes", () => {
    expect(new APIError(500, "PROMPT_TOO_LONG", "").userMessage).toBe(
      "Your prompt is too long. Shorten it and try again.",
    );
    expect(new APIError(500, "ALL_PROVIDERS_FAILED", "").userMessage).toBe(
      "Every AI provider in your chain failed. Check your keys in Settings or try again.",
    );
    expect(new APIError(500, "BEAT_DETECT_FAILED", "").userMessage).toBe(
      "Couldn't analyze the song's beat. Try a different audio file.",
    );
    expect(new APIError(500, "NO_CUTLIST", "").userMessage).toBe(
      "This project has no timeline yet. Generate or import one first.",
    );
  });

  it("collapses infra-unavailable codes into a shared message", () => {
    const msg = "Service temporarily unavailable. Try again in a moment.";
    expect(new APIError(500, "DB_UNAVAILABLE", "").userMessage).toBe(msg);
    expect(new APIError(500, "REDIS_UNAVAILABLE", "").userMessage).toBe(msg);
    expect(new APIError(500, "TEMPORAL_UNAVAILABLE", "").userMessage).toBe(msg);
    expect(new APIError(500, "R2_UNAVAILABLE", "").userMessage).toBe(msg);
  });
});
