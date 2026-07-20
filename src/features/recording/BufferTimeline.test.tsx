import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import BufferTimeline from "./BufferTimeline";

describe("BufferTimeline", () => {
  it("shows filled time capped at the rolling window and formats mm:ss", () => {
    render(<BufferTimeline recordSec={90} eventMarkers={[]} />);
    expect(screen.getByText("1:30 / 2:00")).toBeInTheDocument();
    expect(screen.getByText("45/60 seg")).toBeInTheDocument();
  });

  it("caps the filled display at the window size once recording exceeds it", () => {
    render(<BufferTimeline recordSec={600} eventMarkers={[]} />);
    expect(screen.getByText("2:00 / 2:00")).toBeInTheDocument();
    expect(screen.getByText("60/60 seg")).toBeInTheDocument();
  });

  it("only renders event pins whose age is still inside the rolling window", () => {
    // window=120s, recordSec=200: sec=190 → age=10 (visible); sec=10 → age=190 (aged out).
    const { container } = render(
      <BufferTimeline recordSec={200} eventMarkers={[{ sec: 190, tag: "recent" }, { sec: 10, tag: "aged-out" }]} />,
    );
    const pins = container.querySelectorAll("[title]");
    expect(pins).toHaveLength(1);
    expect(pins[0].getAttribute("title")).toBe("recent");
  });
});
