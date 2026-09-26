// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

afterEach(cleanup);

describe("Button", () => {
  it("defaults to type button and primary tokens", () => {
    render(<Button>Go</Button>);
    const b = screen.getByRole("button", { name: "Go" });
    expect(b.getAttribute("type")).toBe("button");
    expect(b.className).toContain("bg-accent");
    expect(b.className).toContain("text-on-accent");
  });
  it("applies secondary and ghost tokens", () => {
    render(
      <>
        <Button variant="secondary">S</Button>
        <Button variant="ghost">G</Button>
      </>,
    );
    expect(screen.getByText("S").className).toContain("border-line");
    expect(screen.getByText("G").className).toContain("bg-transparent");
  });
  it("blocks clicks when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        X
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });
  it("renders a link with href", () => {
    render(<Button href="/a">Link</Button>);
    const a = screen.getByRole("link", { name: "Link" });
    expect(a.getAttribute("href")).toBe("/a");
  });
});
