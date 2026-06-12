import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Asset, Project } from "@/types/api";
import { EditorLayout } from "./EditorLayout";

vi.mock("@clerk/nextjs", () => ({
  useUser: () => ({ user: { firstName: "Test" } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api/client", () => ({
  useApi: () => ({
    projects: {
      updateCutlist: vi.fn(),
      prompt: vi.fn(),
      transcribe: vi.fn(),
    },
  }),
}));

vi.mock("./PresenceCursors", () => ({
  PresenceCursors: () => null,
}));

vi.mock("./ProgressBar", () => ({
  ProgressBar: () => null,
}));

vi.mock("./panels/InspectorPanel", () => ({
  InspectorPanel: () => null,
}));

vi.mock("./panels/MediaPanel", () => ({
  MediaPanel: () => null,
}));

vi.mock("./panels/PreviewPanel", () => ({
  PreviewPanel: () => null,
}));

vi.mock("./panels/TimelinePanel", () => ({
  TimelinePanel: () => null,
}));

vi.mock("./RenderButton", () => ({
  RenderButton: () => null,
}));

vi.mock("./SaveStatusBadge", () => ({
  SaveStatusBadge: () => null,
}));

vi.mock("./TemplateSaveDialog", () => ({
  TemplateSaveDialog: () => null,
}));

vi.mock("./TemplateLoadDialog", () => ({
  TemplateLoadDialog: () => null,
}));

vi.mock("@/components/cmdk/CommandPalette", () => ({
  CommandPalette: () => null,
  useCommandPalette: () => ({ open: false, setOpen: vi.fn() }),
}));

function makeProject(styleTier: string): Project {
  return {
    id: "proj-1",
    name: "Test Project",
    status: "uploading",
    styleTier,
    mode: "auto",
    referenceAssetId: null,
    songAssetId: null,
    clipAssetIds: [],
    cutList: null,
    renderAssetId: null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

function makeAssets(): Asset[] {
  return [
    {
      id: "asset-1",
      projectId: "proj-1",
      type: "clip",
      filename: "clip.mp4",
      mimeType: "video/mp4",
      sizeBytes: 1000,
      durationSec: 5,
      width: 1080,
      height: 1920,
      fps: 30,
      storageKey: "key-1",
      storageUrl: null,
      metadata: {},
      createdAt: new Date().toISOString(),
    },
  ];
}

function Wrapper({ styleTier }: { styleTier: string }) {
  // Intentionally create a new assets array reference on every render to
  // exercise the effect-dependency path that previously caused a render storm.
  const assets = makeAssets();
  return <EditorLayout project={makeProject(styleTier)} assets={assets} />;
}

describe("EditorLayout", () => {
  it.each([
    ["cuts_only"],
    ["color_grade"],
    ["with_text"],
    ["with_effects"],
    ["full_remix"],
  ])("mounts without infinite render loop for styleTier=%s", (styleTier) => {
    // React throws "Maximum update depth exceeded" synchronously during render
    // if an effect storm is triggered. If we get through 50 renders without an
    // exception, the dependency fix is working.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = render(<Wrapper styleTier={styleTier} />);

    for (let i = 0; i < 50; i++) {
      rerender(<Wrapper styleTier={styleTier} />);
    }

    const infiniteLoopError = spy.mock.calls.find(
      (call) => typeof call[0] === "string" && call[0].includes("Maximum update depth exceeded"),
    );
    spy.mockRestore();
    expect(infiniteLoopError).toBeUndefined();
  });
});
