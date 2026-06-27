// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RenderOptionsDialog } from "@/components/editor/RenderOptionsDialog";

const mockApi = {
  renders: {
    start: vi.fn().mockResolvedValue({ job: { id: "job-1" } }),
  },
};

vi.mock("@/lib/api/client", () => ({
  useApi: () => mockApi,
}));

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: vi.fn().mockResolvedValue("token") }),
}));

describe("RenderOptionsDialog", () => {
  it("submits durationSec when set", async () => {
    const user = userEvent.setup();
    render(<RenderOptionsDialog open projectId="project-1" onOpenChange={() => {}} />);

    const durationInput = screen.getByPlaceholderText("Auto");
    await user.clear(durationInput);
    await user.type(durationInput, "22");

    const submitButton = screen.getByRole("button", { name: /start render/i });
    await user.click(submitButton);

    expect(mockApi.renders.start).toHaveBeenCalledWith("project-1", {
      durationSec: 22,
    });
  });

  it("does not submit durationSec when left empty", async () => {
    mockApi.renders.start.mockClear();
    const user = userEvent.setup();
    render(<RenderOptionsDialog open projectId="project-1" onOpenChange={() => {}} />);

    const submitButton = screen.getByRole("button", { name: /start render/i });
    await user.click(submitButton);

    expect(mockApi.renders.start).toHaveBeenCalledWith("project-1", {});
  });
});
