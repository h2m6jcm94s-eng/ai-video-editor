import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Asset } from "@/types/api";
import { RenderButton } from "./RenderButton";

const start = vi.fn();

vi.mock("@/lib/api/client", () => ({
  useApi: () => ({
    renders: { start },
  }),
}));

vi.mock("@/hooks/useRenderStatus", () => ({
  useRenderStatus: () => ({ activeRender: null, isRendering: false }),
}));

function makeAssets(types: Asset["type"][]): Asset[] {
  return types.map((type, i) => ({
    id: `asset-${i}`,
    projectId: "proj-1",
    type,
    filename: `${type}.mp4`,
    mimeType: type === "song" ? "audio/mpeg" : "video/mp4",
    sizeBytes: 1000,
    durationSec: 5,
    width: 1080,
    height: 1920,
    fps: 30,
    storageKey: `key-${i}`,
    storageUrl: null,
    metadata: {},
    createdAt: new Date().toISOString(),
  }));
}

describe("RenderButton", () => {
  beforeEach(() => {
    start.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("opens the render options dialog when clicked", async () => {
    const user = userEvent.setup();
    render(<RenderButton projectId="proj-1" assets={makeAssets(["song", "reference_video", "clip"])} />);

    await user.click(screen.getByRole("button", { name: /render/i }));
    expect(screen.getByText("Render Video")).toBeInTheDocument();
  });

  it("starts a render with the default export preset", async () => {
    start.mockResolvedValueOnce({ job: { id: "job-1" } });
    const user = userEvent.setup();
    render(<RenderButton projectId="proj-1" assets={makeAssets(["song", "reference_video", "clip"])} />);

    await user.click(screen.getByRole("button", { name: /render/i }));
    await user.click(screen.getByRole("button", { name: /start render/i }));

    await waitFor(() => expect(start).toHaveBeenCalledWith("proj-1", { exportPreset: "reels_9_16" }));
  });

  it("disables the button when required assets are missing", () => {
    render(<RenderButton projectId="proj-1" assets={makeAssets(["song"])} />);
    expect(screen.getByRole("button", { name: /render/i })).toBeDisabled();
  });
});
