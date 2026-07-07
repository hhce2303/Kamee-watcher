import { beforeEach, describe, expect, it, vi } from "vitest";
import { initAppStore, useAppStore } from "./appStore";
import { emitFake, invoke } from "../test/tauriMocks";

describe("appStore", () => {
  beforeEach(() => {
    useAppStore.setState({
      ipcConnected: false,
      settings: null,
      policy: useAppStore.getState().policy,
      logs: [],
      unreadCount: 0,
      drawerOpen: false,
      lastError: null,
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

  it("log_message and recording_failed push into log history, newest first", () => {
    invoke.mockImplementation(async () => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const cleanup = initAppStore();
    emitFake("log_message", { event: "log_message", message: "hello" });
    emitFake("recording_failed", { event: "recording_failed", message: "ffmpeg died" });

    const logs = useAppStore.getState().logs;
    expect(logs.map((n) => n.message)).toEqual(["ffmpeg died", "hello"]);
    expect(logs[0].level).toBe("error");
    expect(useAppStore.getState().unreadCount).toBe(2);
    expect(useAppStore.getState().lastError?.message).toBe("ffmpeg died");
    cleanup();
    errorSpy.mockRestore();
  });

  it("toggleLogDrawer opens the drawer, clears unread count and the pinned error", () => {
    useAppStore.setState({
      logs: [{ id: 1, message: "boom", level: "error", ts: 0 }],
      unreadCount: 3,
      lastError: { id: 1, message: "boom", level: "error", ts: 0 },
      drawerOpen: false,
    });
    useAppStore.getState().toggleLogDrawer();
    expect(useAppStore.getState().drawerOpen).toBe(true);
    expect(useAppStore.getState().unreadCount).toBe(0);
    expect(useAppStore.getState().lastError).toBeNull();

    useAppStore.getState().toggleLogDrawer();
    expect(useAppStore.getState().drawerOpen).toBe(false);
  });
});
