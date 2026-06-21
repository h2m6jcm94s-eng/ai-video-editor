import { render, waitFor } from "@testing-library/react";
import type { Mock } from "vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PresenceCursors } from "./PresenceCursors";

interface ReportMock {
  (): Promise<void>;
  resolve: () => void;
}

const report = vi.fn(
  () =>
    new Promise<void>((resolve) => {
      (report as unknown as ReportMock).resolve = resolve;
    }),
) as unknown as Mock & ReportMock;

const api = {
  presence: {
    report,
    get: vi.fn().mockResolvedValue({
      users: [{ userId: "u1", name: "Alice", color: "#f00", x: 0, y: 0 }],
    }),
  },
};

vi.mock("@/lib/api/client", () => ({
  useApi: () => api,
}));

function fireMouseMove() {
  window.dispatchEvent(new MouseEvent("mousemove", { clientX: 100, clientY: 100 }));
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("PresenceCursors", () => {
  afterEach(() => {
    report.mockClear();
  });

  it("debounces mousemove reports and aborts the previous request", async () => {
    const { container } = render(<PresenceCursors projectId="p1" userName="Bob" />);
    await waitFor(() => expect(container.querySelector("svg")).toBeInTheDocument());

    fireMouseMove();
    await wait(100);

    expect(report).toHaveBeenCalledTimes(1);
    const firstSignal = (report.mock.calls[0] as [string, object, { signal: AbortSignal }])[2].signal;
    expect(firstSignal.aborted).toBe(false);

    fireMouseMove();
    await wait(100);

    expect(report).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(firstSignal.aborted).toBe(true));
  });

  it("does not schedule another report while the pointer is moving", async () => {
    const { container } = render(<PresenceCursors projectId="p1" userName="Bob" />);
    await waitFor(() => expect(container.querySelector("svg")).toBeInTheDocument());

    fireMouseMove();
    await wait(50);
    expect(report).toHaveBeenCalledTimes(0);

    fireMouseMove();
    await wait(50);
    expect(report).toHaveBeenCalledTimes(0);

    await wait(100);
    expect(report).toHaveBeenCalledTimes(1);
  });
});
