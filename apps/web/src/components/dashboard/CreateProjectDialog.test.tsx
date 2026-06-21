import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CreateProjectDialog } from "./CreateProjectDialog";

const create = vi.fn();
const push = vi.fn();

vi.mock("@/lib/api/client", () => ({
  useApi: () => ({
    projects: { create },
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("CreateProjectDialog", () => {
  beforeEach(() => {
    create.mockReset();
    push.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("closes the dialog after a successful project creation", async () => {
    create.mockResolvedValueOnce({ project: { id: "proj-123" } });
    const user = userEvent.setup();
    render(<CreateProjectDialog />);

    await user.click(screen.getByRole("button", { name: /new project/i }));
    expect(screen.getByText("Create New Project")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("My Awesome Edit"), "Test Project");
    await user.click(screen.getByTestId("create-project-submit"));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        name: "Test Project",
        styleTier: "with_effects",
        mode: "auto",
      }),
    );
    expect(push).toHaveBeenCalledWith("/editor/proj-123");
    await waitFor(() => expect(screen.queryByText("Create New Project")).not.toBeInTheDocument());
  });

  it("closes the dialog when cancel is clicked", async () => {
    const user = userEvent.setup();
    render(<CreateProjectDialog />);

    await user.click(screen.getByRole("button", { name: /new project/i }));
    expect(screen.getByText("Create New Project")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByText("Create New Project")).not.toBeInTheDocument());
  });
});
