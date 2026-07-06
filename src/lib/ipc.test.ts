import { describe, expect, it } from "vitest";
import { invoke } from "../test/tauriMocks";
import {
  getMediaRoots,
  getSettings,
  ipcSend,
  listClips,
  setAutostart,
  toggleMonitor,
  triggerEvent,
} from "./ipc";

describe("ipc command wrappers", () => {
  it("ipcSend proxies through the ipc_send Tauri command with cmd/payload shape", async () => {
    await ipcSend("some_cmd", { a: 1 });
    expect(invoke).toHaveBeenCalledWith("ipc_send", { cmd: "some_cmd", payload: { a: 1 } });
  });

  it("defaults payload to {} when omitted", async () => {
    await ipcSend("no_payload_cmd");
    expect(invoke).toHaveBeenCalledWith("ipc_send", { cmd: "no_payload_cmd", payload: {} });
  });

  it("triggerEvent sends the exact router command name", async () => {
    await triggerEvent();
    expect(invoke).toHaveBeenCalledWith("ipc_send", { cmd: "trigger_event", payload: {} });
  });

  it("toggleMonitor forwards the fingerprint payload", async () => {
    await toggleMonitor("abc123");
    expect(invoke).toHaveBeenCalledWith("ipc_send", {
      cmd: "toggle_monitor",
      payload: { fingerprint: "abc123" },
    });
  });

  it("listClips sends no payload", async () => {
    await listClips();
    expect(invoke).toHaveBeenCalledWith("ipc_send", { cmd: "list_clips", payload: {} });
  });

  it("getSettings / getMediaRoots match the router.py command names", async () => {
    await getSettings();
    expect(invoke).toHaveBeenCalledWith("ipc_send", { cmd: "get_settings", payload: {} });
    await getMediaRoots();
    expect(invoke).toHaveBeenCalledWith("ipc_send", { cmd: "get_media_roots", payload: {} });
  });

  it("setAutostart forwards the enabled flag", async () => {
    await setAutostart(true);
    expect(invoke).toHaveBeenCalledWith("ipc_send", {
      cmd: "set_autostart",
      payload: { enabled: true },
    });
  });
});
