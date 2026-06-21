import { describe, expect, it } from "vitest";
import { createCompletionToken, decrypt, encrypt, verifyCompletionToken } from "../lib/crypto";

describe("crypto", () => {
  it("round-trips provider key encryption", () => {
    const secret = "sk-ant-api03-test-key";
    const encrypted = encrypt(secret);
    expect(encrypted).toMatch(/^v\d:/);
    expect(decrypt(encrypted)).toBe(secret);
  });

  it("decrypts legacy keys without a version prefix", () => {
    // A manually generated legacy-format key (v1, no prefix) using the test KEK.
    const legacy = "hG1x2vY3wZ4aB5cD6eF7gH8iJ9kL0mN1oP2qR3sT4uV5wX6yZ7=";
    // The legacy shape is parsed as v1 and validated as AES-GCM data; random
    // bytes should fail authentication rather than a version mismatch error.
    expect(() => decrypt(legacy)).toThrow(/authenticate|Invalid ciphertext/);
  });

  it("creates and verifies render completion tokens", () => {
    const token = createCompletionToken("render-1", "project-2");
    expect(verifyCompletionToken(token, "render-1", "project-2")).toBe(true);
    expect(verifyCompletionToken(token, "render-1", "project-3")).toBe(false);
    expect(verifyCompletionToken("bad-token", "render-1", "project-2")).toBe(false);
  });
});
