// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Card } from "./Card";
import { Tag } from "./Tag";

afterEach(cleanup);

describe("Tag", () => {
  it("renders text", () => {
    render(<Tag>ai</Tag>);
    expect(screen.getByText("ai").className).toContain("rounded-pill");
  });
  it("renders a link with href", () => {
    render(<Tag href="/t/ai">ai</Tag>);
    expect(screen.getByRole("link", { name: "ai" }).getAttribute("href")).toBe(
      "/t/ai",
    );
  });
});

describe("Card", () => {
  it("adds hover shadow only when interactive", () => {
    render(
      <>
        <Card data-testid="a">a</Card>
        <Card data-testid="b" interactive>
          b
        </Card>
      </>,
    );
    expect(screen.getByTestId("a").className).not.toContain(
      "hover:shadow-hover",
    );
    expect(screen.getByTestId("b").className).toContain("hover:shadow-hover");
  });
});
