import {
  ASSET_TYPE,
  createProjectSchema,
  createRenderSchema,
  createTemplateSchema,
  cutListSchema,
  EDIT_MODE,
  patchProjectSchema,
  presignedUploadSchema,
  promptEditSchema,
  providerEncryptedKeySchema,
  providerKeySchema,
  STYLE_TIER,
  testProviderKeySchema,
} from "@ai-video-editor/shared-types";
import { describe, expect, it } from "vitest";

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
    expect(STYLE_TIER).toEqual(["cuts_only", "color_grade", "with_text", "with_effects", "full_remix"]);
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
      }).success,
    ).toBe(true);

    expect(
      presignedUploadSchema.safeParse({
        projectId: "550e8400-e29b-41d4-a716-446655440000",
        filename: "video.mp4",
        mimeType: "application/exe",
        type: "clip",
      }).success,
    ).toBe(false);
  });

  it("createRenderSchema requires valid UUID", () => {
    expect(
      createRenderSchema.safeParse({
        projectId: "550e8400-e29b-41d4-a716-446655440000",
      }).success,
    ).toBe(true);

    expect(createRenderSchema.safeParse({ projectId: "not-a-uuid" }).success).toBe(false);
  });

  it("createTemplateSchema requires trimmed name", () => {
    const validCutList = {
      globals: { totalDurationS: 30, tempoBpm: 120 },
      slots: [
        {
          index: 0,
          startS: 0,
          durationS: 5,
          beatIndex: 0,
          section: "intro",
          targetShotType: "medium",
          subjectHint: "person",
          motionHint: "static",
        },
      ],
    };
    expect(createTemplateSchema.safeParse({ name: "Template A", cutList: validCutList }).success).toBe(true);
    expect(createTemplateSchema.safeParse({ name: "   ", cutList: validCutList }).success).toBe(false);
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

  it("patchProjectSchema rejects internal fields", () => {
    expect(patchProjectSchema.safeParse({ status: "completed" }).success).toBe(false);
    expect(patchProjectSchema.safeParse({ userId: "550e8400-e29b-41d4-a716-446655440000" }).success).toBe(
      false,
    );
    expect(
      patchProjectSchema.safeParse({ renderAssetId: "550e8400-e29b-41d4-a716-446655440000" }).success,
    ).toBe(false);
  });

  it("providerEncryptedKeySchema validates base64 payload length", () => {
    expect(providerEncryptedKeySchema.safeParse("dGVzdC1rZXktd2l0aC1tb3JlLWJ5dGVz").success).toBe(true);
    expect(providerEncryptedKeySchema.safeParse("not base64!").success).toBe(false);
    expect(providerEncryptedKeySchema.safeParse("a").success).toBe(false);
  });

  it("testProviderKeySchema requires provider", () => {
    expect(testProviderKeySchema.safeParse({ provider: "openai" }).success).toBe(true);
    expect(testProviderKeySchema.safeParse({}).success).toBe(false);
  });

  it("ASSET_TYPE includes lut + sfx", () => {
    expect(ASSET_TYPE).toContain("lut");
    expect(ASSET_TYPE).toContain("sfx");
  });
});

describe("Contract tests — cutList camelCase invariant", () => {
  it("rejects snake_case keys", () => {
    const bad = {
      globals: {
        totalDurationS: 10,
        tempoBpm: 120,
        timeSignature: "4/4",
        energyCurve: [],
        sectionMarkers: [],
        aspectRatio: "9:16",
      },
      slots: [{ start_s: 0, duration_s: 5 }],
    };
    expect(cutListSchema.safeParse(bad).success).toBe(false);
  });

  it("accepts camelCase keys", () => {
    const good = {
      globals: {
        totalDurationS: 10,
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
          targetShotType: "medium",
          subjectHint: "person",
          motionHint: "static",
          energyLevel: 0.5,
          requiredTags: [],
          avoidTags: [],
        },
      ],
      overlays: [],
      audioTracks: [],
    };
    expect(cutListSchema.safeParse(good).success).toBe(true);
  });

  it("rejects extra fields when .strict()", () => {
    const withExtra = {
      globals: {
        totalDurationS: 10,
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
          targetShotType: "medium",
          subjectHint: "person",
          motionHint: "static",
          energyLevel: 0.5,
          requiredTags: [],
          avoidTags: [],
          evil: true,
        },
      ],
      overlays: [],
      audioTracks: [],
    };
    expect(cutListSchema.safeParse(withExtra).success).toBe(false);
  });
});
