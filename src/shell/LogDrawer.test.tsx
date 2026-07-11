import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import LogDrawer from "./LogDrawer";
import { useAppStore } from "../stores/appStore";

describe("LogDrawer", () => {
  beforeEach(() => {
    useAppStore.setState({ logs: [], unreadCount: 0, drawerOpen: true });
  });

  it("renders a warning-level entry with the warning row class, distinct from info/error", () => {
    useAppStore.setState({
      logs: [
        { id: 1, message: "recording degraded", level: "warning", ts: 0 },
        { id: 2, message: "hello", level: "info", ts: 0 },
        { id: 3, message: "boom", level: "error", ts: 0 },
      ],
    });
    render(<LogDrawer />);

    const warningRow = screen.getByText("recording degraded").closest(".log-drawer__row");
    const infoRow = screen.getByText("hello").closest(".log-drawer__row");
    const errorRow = screen.getByText("boom").closest(".log-drawer__row");

    expect(warningRow).toHaveClass("log-drawer__row--warning");
    expect(warningRow).not.toHaveClass("log-drawer__row--error");
    expect(infoRow).not.toHaveClass("log-drawer__row--warning");
    expect(infoRow).not.toHaveClass("log-drawer__row--error");
    expect(errorRow).toHaveClass("log-drawer__row--error");
  });
});
