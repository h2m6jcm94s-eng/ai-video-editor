// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Project } from "@/types/api";
import { StatsSection } from "./StatsSection";

vi.mock("@/hooks/useCountUp", () => ({
  useCountUp: (value: number) => value,
}));

function makeProject(status: Project["status"], renderAssetId: string | null = null): Project {
  return {
    id: `proj-${status}`,
    name: "Test",
    status,
    styleTier: "with_effects",
    mode: "auto",
    referenceAssetId: null,
    songAssetId: null,
    clipAssetIds: [],
    cutList: null,
    renderAssetId,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

describe("StatsSection", () => {
  it("renders all stat cards with correct counts", () => {
    const projects: Project[] = [
      makeProject("complete", "render-1"),
      makeProject("uploading"),
      makeProject("processing"),
      makeProject("failed"),
    ];

    render(<StatsSection projects={projects} />);

    expect(screen.getByText("Total Projects")).toBeInTheDocument();
    expect(screen.getByTestId("stat-Total Projects")).toHaveTextContent("4");

    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByTestId("stat-In Progress")).toHaveTextContent("2");

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByTestId("stat-Completed")).toHaveTextContent("1");

    expect(screen.getByText("Rendered")).toBeInTheDocument();
    expect(screen.getByTestId("stat-Rendered")).toHaveTextContent("1");
  });

  it("handles an empty project list", () => {
    render(<StatsSection projects={[]} />);
    expect(screen.getAllByText("0")).toHaveLength(4);
  });
});
