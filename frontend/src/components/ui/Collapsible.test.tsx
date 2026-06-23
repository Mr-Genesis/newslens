import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Collapsible } from "./Collapsible";

describe("Collapsible (v4 brief-by-default)", () => {
  it("is collapsed by default and shows the preview", () => {
    render(
      <Collapsible label="SUMMARY" preview="preview text">
        <p>BODY CONTENT</p>
      </Collapsible>
    );
    expect(screen.getByText("preview text")).toBeInTheDocument();
    expect(screen.queryByText("BODY CONTENT")).toBeNull();
  });

  it("expands on click", async () => {
    render(
      <Collapsible label="SUMMARY" preview="preview text">
        <p>BODY CONTENT</p>
      </Collapsible>
    );
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByText("BODY CONTENT")).toBeInTheDocument();
  });

  it("respects defaultOpen", () => {
    render(
      <Collapsible label="SOURCES" defaultOpen>
        <p>OPEN BODY</p>
      </Collapsible>
    );
    expect(screen.getByText("OPEN BODY")).toBeInTheDocument();
  });
});
