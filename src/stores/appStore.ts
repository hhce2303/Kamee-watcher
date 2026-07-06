import { create } from "zustand";
import { getSettings } from "../lib/ipc";
import { listen } from "@tauri-apps/api/event";
import { policyFor, type RolePolicy } from "../lib/policy";
import type { BackendEventMap, SettingsSnapshot } from "../types/dto";

export interface Notification {
  id: number;
  message: string;
  level: "info" | "error";
}

interface AppState {
  ipcConnected: boolean;
  settings: SettingsSnapshot | null;
  policy: RolePolicy;
  notifications: Notification[];
  activeTab: number;
  setActiveTab: (tab: number) => void;
  dismissNotification: (id: number) => void;
}

let nextNotificationId = 1;

export const useAppStore = create<AppState>((set, get) => ({
  ipcConnected: false,
  settings: null,
  policy: policyFor(""),
  notifications: [],
  activeTab: 0,
  setActiveTab: (tab) => set({ activeTab: tab }),
  dismissNotification: (id) =>
    set({ notifications: get().notifications.filter((n) => n.id !== id) }),
}));

function pushNotification(message: string, level: Notification["level"]): void {
  const notification: Notification = { id: nextNotificationId++, message, level };
  useAppStore.setState((s) => ({ notifications: [...s.notifications, notification] }));
}

async function refreshSettings(): Promise<void> {
  try {
    const settings = await getSettings();
    useAppStore.setState({ settings, policy: policyFor(settings.role) });
  } catch (e) {
    console.error("appStore: get_settings failed", e);
  }
}

/**
 * Wire the store to the Tauri event bus. Call once at app startup (App.tsx) —
 * not a hook, since this state is genuinely global (role/policy/connection
 * are needed by the shell, the tray-adjacent REC pill, and a second window).
 */
export function initAppStore(): () => void {
  const unlisteners: Promise<() => void>[] = [];

  unlisteners.push(
    listen("ipc_connected", () => {
      useAppStore.setState({ ipcConnected: true });
      void refreshSettings();
    }),
  );
  unlisteners.push(listen("ipc_disconnected", () => useAppStore.setState({ ipcConnected: false })));

  unlisteners.push(
    listen<BackendEventMap["role_changed"]>("role_changed", (e) => {
      useAppStore.setState((s) => ({
        policy: policyFor(e.payload.role),
        settings: s.settings ? { ...s.settings, role: e.payload.role, it_unlocked: e.payload.it_unlocked } : s.settings,
      }));
    }),
  );

  unlisteners.push(
    listen<BackendEventMap["log_message"]>("log_message", (e) => pushNotification(e.payload.message, "info")),
  );
  unlisteners.push(
    listen<BackendEventMap["recording_failed"]>("recording_failed", (e) =>
      pushNotification(e.payload.message, "error"),
    ),
  );
  unlisteners.push(
    listen<BackendEventMap["clip_failed"]>("clip_failed", (e) => pushNotification(e.payload.message, "error")),
  );

  // In case the pipe is already connected by the time this runs.
  void refreshSettings();

  return () => {
    unlisteners.forEach((p) => p.then((fn) => fn()));
  };
}
