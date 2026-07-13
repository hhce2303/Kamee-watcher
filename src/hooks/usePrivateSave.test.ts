import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { usePrivateSave } from "./usePrivateSave";
import { emitFake, invoke } from "../test/tauriMocks";

describe("usePrivateSave", () => {
  it("save() goes idle -> working -> saved via push events", async () => {
    invoke.mockImplementation(async () => undefined);
    const { result } = renderHook(() => usePrivateSave());
    expect(result.current.state).toBe("idle");

    await act(async () => {
      await result.current.save();
    });
    expect(result.current.state).toBe("working");

    act(() => {
      emitFake("onedrive_save_started", { event: "onedrive_save_started" });
    });
    await waitFor(() => expect(result.current.state).toBe("working"));
    expect(result.current.progress).toBe(0);

    act(() => {
      emitFake("export_progress", { event: "export_progress", fraction: 0.6 });
    });
    await waitFor(() => expect(result.current.progress).toBe(0.6));

    act(() => {
      emitFake("onedrive_saved", {
        event: "onedrive_saved",
        folder_path: "SLC/clips-supervisor/2026-07",
        output_path: "SLC/clips-supervisor/2026-07/reel_2026-07-13_10-00-00.mp4",
      });
    });
    await waitFor(() => expect(result.current.state).toBe("saved"));
    expect(result.current.folder).toBe("SLC/clips-supervisor/2026-07");
    expect(result.current.outputPath).toBe("SLC/clips-supervisor/2026-07/reel_2026-07-13_10-00-00.mp4");
  });

  it("reflects onedrive_save_failed as an error state", async () => {
    invoke.mockImplementation(async () => undefined);
    const { result } = renderHook(() => usePrivateSave());

    act(() => {
      emitFake("onedrive_save_failed", { event: "onedrive_save_failed", message: "boom" });
    });
    await waitFor(() => expect(result.current.state).toBe("error"));
    expect(result.current.error).toBe("boom");
  });

  it("reset() clears state back to idle", async () => {
    invoke.mockImplementation(async () => undefined);
    const { result } = renderHook(() => usePrivateSave());

    act(() => {
      emitFake("onedrive_saved", {
        event: "onedrive_saved",
        folder_path: "f",
        output_path: "f/reel.mp4",
      });
    });
    await waitFor(() => expect(result.current.state).toBe("saved"));

    act(() => result.current.reset());
    expect(result.current.state).toBe("idle");
    expect(result.current.folder).toBe("");
    expect(result.current.outputPath).toBe("");
    expect(result.current.progress).toBe(0);
  });
});
