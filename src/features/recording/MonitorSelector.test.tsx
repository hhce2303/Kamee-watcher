import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import MonitorSelector from "./MonitorSelector";
import type { MonitorDTO } from "../../types/dto";

function monitor(overrides: Partial<MonitorDTO> = {}): MonitorDTO {
  return {
    name: "DISPLAY1",
    device_name: "\\\\.\\DISPLAY1",
    resolution: "1920x1080",
    fingerprint: "fp-1",
    index: 0,
    x: 0,
    y: 0,
    is_primary: true,
    selected: false,
    ...overrides,
  };
}

describe("MonitorSelector", () => {
  it("shows the empty state when there are no monitors", () => {
    render(<MonitorSelector monitors={[]} onToggle={() => {}} />);
    expect(screen.getByText("Sin pantallas detectadas")).toBeInTheDocument();
  });

  it("renders the active/total count in the header", () => {
    const monitors = [monitor({ selected: true }), monitor({ fingerprint: "fp-2", selected: false })];
    render(<MonitorSelector monitors={monitors} onToggle={() => {}} />);
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  it("exposes each row as an accessible checkbox reflecting selection state", () => {
    const monitors = [monitor({ selected: true }), monitor({ fingerprint: "fp-2", name: "DISPLAY2", selected: false })];
    render(<MonitorSelector monitors={monitors} onToggle={() => {}} />);

    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes[0]).toHaveAttribute("aria-checked", "true");
    expect(checkboxes[1]).toHaveAttribute("aria-checked", "false");
  });

  it("calls onToggle with the monitor's fingerprint on click", async () => {
    const onToggle = vi.fn();
    render(<MonitorSelector monitors={[monitor()]} onToggle={onToggle} />);

    await userEvent.click(screen.getByRole("checkbox"));

    expect(onToggle).toHaveBeenCalledWith("fp-1");
  });

  it("hides the header when showHeader is false", () => {
    render(<MonitorSelector monitors={[monitor()]} onToggle={() => {}} showHeader={false} />);
    expect(screen.queryByText("PANTALLAS")).not.toBeInTheDocument();
  });
});
