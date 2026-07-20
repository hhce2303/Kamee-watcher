import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useOutputPanel } from "./useOutputPanel";
import { invoke } from "../test/tauriMocks";

describe("useOutputPanel", () => {
  it("save() goes idle -> working -> linked on success", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "compute_folder_path") return { path: "SLC/clips-supervisor/2026-07" };
      if (cmd === "ensure_folder_and_link") {
        return { folder_path: "SLC/clips-supervisor/2026-07", share_link: "file:///x" };
      }
      return undefined;
    });

    const { result } = renderHook(() => useOutputPanel());
    expect(result.current.state).toBe("idle");

    await act(async () => {
      await result.current.save();
    });

    expect(result.current.state).toBe("linked");
    expect(result.current.folder).toBe("SLC/clips-supervisor/2026-07");
    expect(result.current.link).toBe("file:///x");
  });

  it("save() goes to error state when ensure_folder_and_link throws", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "compute_folder_path") return { path: "x" };
      if (cmd === "ensure_folder_and_link") throw new Error("OneDrive no está configurado.");
      return undefined;
    });

    const { result } = renderHook(() => useOutputPanel());
    await act(async () => {
      await result.current.save();
    });

    expect(result.current.state).toBe("error");
    expect(result.current.error).toContain("OneDrive no está configurado");
  });

  it("reset() clears state back to idle", async () => {
    invoke.mockImplementation(async () => undefined);
    const { result } = renderHook(() => useOutputPanel());

    await act(async () => {
      await result.current.reset();
    });

    expect(result.current.state).toBe("idle");
    expect(result.current.folder).toBe("");
    expect(result.current.link).toBe("");
  });

  it("reflects onedrive_changed/failed push events", async () => {
    const { emitFake } = await import("../test/tauriMocks");
    const { result } = renderHook(() => useOutputPanel());

    act(() => {
      emitFake("onedrive_changed", { event: "onedrive_changed", state: "linked", folder: "f", link: "l" });
    });
    await waitFor(() => expect(result.current.state).toBe("linked"));
    expect(result.current.folder).toBe("f");

    act(() => {
      emitFake("onedrive_failed", { event: "onedrive_failed", message: "boom" });
    });
    await waitFor(() => expect(result.current.state).toBe("error"));
    expect(result.current.error).toBe("boom");
  });
});
