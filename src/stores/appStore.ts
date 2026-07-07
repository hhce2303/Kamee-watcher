import { create } from "zustand";
import { getSettings } from "../lib/ipc";
import { listen } from "@tauri-apps/api/event";
import { policyFor, type RolePolicy } from "../lib/policy";
import type { BackendEventMap, SettingsSnapshot } from "../types/dto";

export interface LogEntry {
  id: number;
  message: string;
  level: "info" | "error";
  ts: number;
}

interface AppState {
  ipcConnected: boolean;
  settings: SettingsSnapshot | null;
  policy: RolePolicy;
  logs: LogEntry[];
  unreadCount: number;
  drawerOpen: boolean;
  lastError: LogEntry | null;
  activeTab: number;
  setActiveTab: (tab: number) => void;
  toggleLogDrawer: () => void;
}

let nextLogId = 1;

// The backend daemon emits routine INFO chatter constantly (monitor polls, per-clip build
// progress) — logs are a bounded history you check, not toasts you're interrupted by. See
// LogTicker (Statusbar, ambient "something just happened") and LogDrawer (on-demand history).
const MAX_LOG_HISTORY = 50;

export const useAppStore = create<AppState>((set) => ({
  ipcConnected: false,
  settings: null,
  policy: policyFor(""),
  logs: [],
  unreadCount: 0,
  drawerOpen: false,
  lastError: null,
  activeTab: 0,
  setActiveTab: (tab) => set({ activeTab: tab }),
  toggleLogDrawer: () =>
    set((s) => {
      const opening = !s.drawerOpen;
      // Opening the drawer is how the user acknowledges an error — it stops pinning the
      // ticker and clears the unread badge, same as reading your notifications.
      return { drawerOpen: opening, unreadCount: opening ? 0 : s.unreadCount, lastError: opening ? null : s.lastError };
    }),
}));

function pushLog(message: string, level: LogEntry["level"]): void {
  const entry: LogEntry = { id: nextLogId++, message, level, ts: Date.now() };
  useAppStore.setState((s) => ({
    logs: [entry, ...s.logs].slice(0, MAX_LOG_HISTORY),
    lastError: level === "error" ? entry : s.lastError,
    unreadCount: s.drawerOpen ? s.unreadCount : s.unreadCount + 1,
  }));
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
    listen<BackendEventMap["log_message"]>("log_message", (e) => pushLog(e.payload.message, "info")),
  );
  unlisteners.push(
    listen<BackendEventMap["recording_failed"]>("recording_failed", (e) => pushLog(e.payload.message, "error")),
  );
  unlisteners.push(
    listen<BackendEventMap["clip_failed"]>("clip_failed", (e) => pushLog(e.payload.message, "error")),
  );

  // In case the pipe is already connected by the time this runs.
  void refreshSettings();

  return () => {
    unlisteners.forEach((p) => p.then((fn) => fn()));
  };
}
