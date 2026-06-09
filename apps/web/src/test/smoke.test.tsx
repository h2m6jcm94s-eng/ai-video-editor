import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

describe("Frontend test scaffold", () => {
  it("renders a basic React component", () => {
    render(<div data-testid="smoke">Hello from Vitest + RTL</div>);
    expect(screen.getByTestId("smoke")).toHaveTextContent("Hello from Vitest + RTL");
  });
});
