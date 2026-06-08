import { describe, it, expect } from "vitest";
import {
  createProjectSchema,
  patchProjectSchema,
  promptEditSchema,
  presignedUploadSchema,
  createRenderSchema,
  createTemplateSchema,
  providerKeySchema,
  testProviderKeySchema,
} from "@ai-video-editor/shared-types";
import { STYLE_TIER, EDIT_MODE, ASSET_TYPE } from "@ai-video-editor/shared-types";

describe("Contract tests — shared schemas match backend expectations", () => {
  it("createProjectSchema accepts valid project", () => {
    const valid = { name: "My project", styleTier: "with_effects", mode: "auto" };
    expect(createProjectSchema.safeParse(valid).success).toBe(true);
  });

  it("createProjectSchema rejects empty name", () => {
    expect(createProjectSchema.safeParse({ name: "   " }).success).toBe(false);
  });

  it("createProjectSchema rejects invalid styleTier", () => {
    expect(createProjectSchema.safeParse({ name: "X", styleTier: "invalid" }).success).toBe(false);
  });

  it("STYLE_TIER contains exactly the 5 ladder tiers", () => {
    expect(STYLE_TIER).toEqual([
      "cuts_only",
      "color_grade",
      "with_text",
      "with_effects",
      "full_remix",
    ]);
  });

  it("EDIT_MODE contains auto and assisted", () => {
    expect(EDIT_MODE).toEqual(["auto", "assisted"]);
  });

  it("ASSET_TYPE contains all known asset types", () => {
    expect(ASSET_TYPE).toContain("reference_video");
    expect(ASSET_TYPE).toContain("song");
    expect(ASSET_TYPE).toContain("clip");
    expect(ASSET_TYPE).toContain("render");
  });

  it("promptEditSchema accepts valid prompt", () => {
    expect(promptEditSchema.safeParse({ prompt: "cut on beat" }).success).toBe(true);
  });

  it("promptEditSchema rejects empty prompt", () => {
    expect(promptEditSchema.safeParse({ prompt: "" }).success).toBe(false);
  });

  it("presignedUploadSchema requires allowed MIME type", () => {
    expect(
      presignedUploadSchema.safeParse({
        projectId: "550e8400-e29b-41d4-a716-446655440000",
        filename: "video.mp4",
        mimeType: "video/mp4",
        type: "clip",
      }).success
    ).toBe(true);

    expect(
      presignedUploadSchema.safeParse({
        projectId: "550e8400-e29b-41d4-a716-446655440000",
        filename: "video.mp4",
        mimeType: "application/exe",
        type: "clip",
      }).success
    ).toBe(false);
  });

  it("createRenderSchema requires valid UUID", () => {
    expect(
      createRenderSchema.safeParse({
        projectId: "550e8400-e29b-41d4-a716-446655440000",
      }).success
    ).toBe(true);

    expect(createRenderSchema.safeParse({ projectId: "not-a-uuid" }).success).toBe(false);
  });

  it("createTemplateSchema requires trimmed name", () => {
    expect(createTemplateSchema.safeParse({ name: "Template A", cutList: {} }).success).toBe(true);
    expect(createTemplateSchema.safeParse({ name: "   ", cutList: {} }).success).toBe(false);
  });

  it("providerKeySchema requires non-empty provider and key", () => {
    expect(providerKeySchema.safeParse({ provider: "anthropic", key: "sk-ant-xxx" }).success).toBe(true);
    expect(providerKeySchema.safeParse({ provider: "", key: "" }).success).toBe(false);
  });

  it("patchProjectSchema allows partial updates", () => {
    expect(patchProjectSchema.safeParse({ name: "New name" }).success).toBe(true);
    expect(patchProjectSchema.safeParse({ styleTier: "cuts_only" }).success).toBe(true);
    expect(patchProjectSchema.safeParse({}).success).toBe(true);
  });

  it("testProviderKeySchema requires provider", () => {
    expect(testProviderKeySchema.safeParse({ provider: "openai" }).success).toBe(true);
    expect(testProviderKeySchema.safeParse({}).success).toBe(false);
  });
});
