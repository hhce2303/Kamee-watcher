import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import DraggableWorkspace from "./DraggableWorkspace";
import type { MonitorDTO } from "../../types/dto";

const STORAGE_KEY = "watcher_monitor_layout_v5";

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
    selected: true,
    ...overrides,
  };
}

describe("DraggableWorkspace", () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("assigns a default grid position to a monitor with no saved layout", () => {
    render(<DraggableWorkspace monitors={[monitor()]} isRecording={false} />);
    const tile = screen.getByRole("group", { name: /DISPLAY1/ });
    // First monitor lands at the default grid origin (2%, 2%) per the
    // PADDING_X/PADDING_Y constants — locks in the layout-init effect.
    expect(tile.style.left).toBe("2%");
    expect(tile.style.top).toBe("2%");
  });

  it("restores a previously saved layout from localStorage instead of the default grid", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ "fp-1": { x: 30, y: 40, w: 20, h: 20, z: 1 } }),
    );
    render(<DraggableWorkspace monitors={[monitor()]} isRecording={false} />);
    const tile = screen.getByRole("group", { name: /DISPLAY1/ });
    expect(tile.style.left).toBe("30%");
    expect(tile.style.top).toBe("40%");
  });

  it("falls back to the default layout when the saved value is corrupt JSON", () => {
    localStorage.setItem(STORAGE_KEY, "{not-json");
    render(<DraggableWorkspace monitors={[monitor()]} isRecording={false} />);
    const tile = screen.getByRole("group", { name: /DISPLAY1/ });
    expect(tile.style.left).toBe("2%");
  });

  it("persists layout changes back to localStorage", () => {
    render(<DraggableWorkspace monitors={[monitor()]} isRecording={false} />);
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    expect(saved["fp-1"]).toMatchObject({ x: 2, y: 2, w: 46, h: 44 });
  });

  it("moves the tile with arrow keys (keyboard equivalent of pointer drag)", async () => {
    render(<DraggableWorkspace monitors={[monitor()]} isRecording={false} />);
    const tile = screen.getByRole("group", { name: /DISPLAY1/ });
    tile.focus();

    await userEvent.keyboard("{ArrowRight}");

    expect(tile.style.left).toBe("4%"); // 2% default + 2% step
    expect(tile.style.top).toBe("2%"); // unchanged
  });

  it("resizes the tile with Shift+arrow keys (keyboard equivalent of pointer resize)", async () => {
    render(<DraggableWorkspace monitors={[monitor()]} isRecording={false} />);
    const tile = screen.getByRole("group", { name: /DISPLAY1/ });
    tile.focus();

    await userEvent.keyboard("{Shift>}{ArrowDown}{/Shift}");

    expect(tile.style.height).toBe("46%"); // 44% default + 2% step
    expect(tile.style.width).toBe("46%"); // unchanged
  });

  it("clamps movement so the tile cannot be dragged past the 100% boundary", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ "fp-1": { x: 99, y: 0, w: 10, h: 10, z: 1 } }),
    );
    render(<DraggableWorkspace monitors={[monitor()]} isRecording={false} />);
    const tile = screen.getByRole("group", { name: /DISPLAY1/ });
    tile.focus();

    await userEvent.keyboard("{ArrowRight}");

    // Clamped to 100 - w (10) = 90, not 99 + 2 = 101.
    expect(tile.style.left).toBe("90%");
  });
});
