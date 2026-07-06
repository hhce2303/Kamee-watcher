import { beforeEach, describe, expect, it, vi } from "vitest";
import { initAppStore, useAppStore } from "./appStore";
import { emitFake, invoke } from "../test/tauriMocks";

describe("appStore", () => {
  beforeEach(() => {
    useAppStore.setState({
      ipcConnected: false,
      settings: null,
      policy: useAppStore.getState().policy,
      notifications: [],
      activeTab: 0,
    });
  });

  it("fetches get_settings and sets policy on ipc_connected", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "get_settings") {
        return {
          role: "operator",
          clips_dir: "C:/clips",
          codec: "hevc",
          driver: "auto",
          autorecord: true,
          autostart: true,
          it_unlocked: false,
        };
      }
      return undefined;
    });

    const cleanup = initAppStore();
    emitFake("ipc_connected", true);
    await vi.waitFor(() => expect(useAppStore.getState().settings?.role).toBe("operator"));

    expect(useAppStore.getState().ipcConnected).toBe(true);
    expect(useAppStore.getState().policy.visibleTabs).toEqual([0]);
    cleanup();
  });

  it("clears ipcConnected on ipc_disconnected", () => {
    invoke.mockImplementation(async () => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const cleanup = initAppStore();
    useAppStore.setState({ ipcConnected: true });
    emitFake("ipc_disconnected", undefined);
    expect(useAppStore.getState().ipcConnected).toBe(false);
    cleanup();
    errorSpy.mockRestore();
  });

  it("role_changed updates policy and merges into settings", () => {
    invoke.mockImplementation(async () => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    useAppStore.setState({
      settings: {
        role: "supervisor",
        clips_dir: "",
        codec: "hevc",
        driver: "auto",
        autorecord: false,
        autostart: false,
        it_unlocked: false,
      },
    });
    const cleanup = initAppStore();
    emitFake("role_changed", { event: "role_changed", role: "it", it_unlocked: true });

    expect(useAppStore.getState().policy.canChangeRole).toBe(true);
    expect(useAppStore.getState().settings?.role).toBe("it");
    expect(useAppStore.getState().settings?.it_unlocked).toBe(true);
    cleanup();
    errorSpy.mockRestore();
  });

  it("log_message and recording_failed push notifications", () => {
    invoke.mockImplementation(async () => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const cleanup = initAppStore();
    emitFake("log_message", { event: "log_message", message: "hello" });
    emitFake("recording_failed", { event: "recording_failed", message: "ffmpeg died" });

    const notes = useAppStore.getState().notifications;
    expect(notes.map((n) => n.message)).toEqual(["hello", "ffmpeg died"]);
    expect(notes[1].level).toBe("error");
    cleanup();
    errorSpy.mockRestore();
  });

  it("dismissNotification removes by id", () => {
    useAppStore.setState({ notifications: [{ id: 1, message: "a", level: "info" }] });
    useAppStore.getState().dismissNotification(1);
    expect(useAppStore.getState().notifications).toEqual([]);
  });
});
