import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import LogTicker from "./LogTicker";
import { useAppStore } from "../stores/appStore";

describe("LogTicker", () => {
  beforeEach(() => {
    useAppStore.setState({ logs: [], lastError: null });
  });

  it("colors a warning-level entry distinctly from info and error", () => {
    useAppStore.setState({
      logs: [{ id: 1, message: "recording degraded", level: "warning", ts: 0 }],
      lastError: null,
    });
    render(<LogTicker />);
    expect(screen.getByText("recording degraded")).toHaveStyle({ color: "var(--accent-yellow)" });
  });

  it("colors an info-level entry with the muted text color", () => {
    useAppStore.setState({
      logs: [{ id: 1, message: "hello", level: "info", ts: 0 }],
      lastError: null,
    });
    render(<LogTicker />);
    expect(screen.getByText("hello")).toHaveStyle({ color: "var(--text-muted)" });
  });

  it("colors a pinned error entry with the record accent", () => {
    useAppStore.setState({
      logs: [],
      lastError: { id: 1, message: "boom", level: "error", ts: 0 },
    });
    render(<LogTicker />);
    expect(screen.getByText("boom")).toHaveStyle({ color: "var(--accent-record)" });
  });
});
