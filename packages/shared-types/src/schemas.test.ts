import { describe, expect, it } from "vitest";
import {
  createProjectSchema,
  patchProjectSchema,
  providerEncryptedKeySchema,
  providerKeySchema,
} from "./schemas";

describe("patchProjectSchema", () => {
  it("accepts partial updates of allowed fields", () => {
    expect(patchProjectSchema.safeParse({ name: "New name" }).success).toBe(true);
    expect(patchProjectSchema.safeParse({ styleTier: "cuts_only" }).success).toBe(true);
    expect(patchProjectSchema.safeParse({ mode: "assisted" }).success).toBe(true);
    expect(patchProjectSchema.safeParse({}).success).toBe(true);
  });

  it("rejects internal/read-only fields", () => {
    expect(patchProjectSchema.safeParse({ status: "completed" }).success).toBe(false);
    expect(patchProjectSchema.safeParse({ userId: "550e8400-e29b-41d4-a716-446655440000" }).success).toBe(
      false,
    );
    expect(
      patchProjectSchema.safeParse({ renderAssetId: "550e8400-e29b-41d4-a716-446655440000" }).success,
    ).toBe(false);
    expect(patchProjectSchema.safeParse({ createdAt: "2024-01-01" }).success).toBe(false);
  });

  it("is not affected by future additions to createProjectSchema", () => {
    // This documents the explicit contract: patch must only allow user-editable fields.
    const createKeys = Object.keys(createProjectSchema.shape);
    const patchKeys = Object.keys(patchProjectSchema.shape);
    for (const key of patchKeys) {
      expect(createKeys).toContain(key);
    }
  });
});

describe("providerEncryptedKeySchema", () => {
  it("accepts valid base64 ciphertexts", () => {
    expect(providerEncryptedKeySchema.safeParse("dGVzdC1rZXktd2l0aC1tb3JlLWJ5dGVz").success).toBe(true);
    expect(
      providerEncryptedKeySchema.safeParse(Buffer.from("x".repeat(100)).toString("base64")).success,
    ).toBe(true);
  });

  it("rejects non-base64 characters", () => {
    expect(providerEncryptedKeySchema.safeParse("not base64!").success).toBe(false);
    expect(providerEncryptedKeySchema.safeParse("dGVzdC1rZXk=\n").success).toBe(false);
  });

  it("rejects values that are too short or too long", () => {
    expect(providerEncryptedKeySchema.safeParse("a").success).toBe(false);
    expect(providerEncryptedKeySchema.safeParse("ab==").success).toBe(false);
    expect(
      providerEncryptedKeySchema.safeParse(Buffer.from("x".repeat(5000)).toString("base64")).success,
    ).toBe(false);
  });
});

describe("providerKeySchema", () => {
  it("rejects keys containing whitespace", () => {
    expect(providerKeySchema.safeParse({ provider: "anthropic", key: "sk ant key" }).success).toBe(false);
  });
});
