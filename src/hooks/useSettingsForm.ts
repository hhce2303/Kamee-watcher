import { useCallback, useEffect, useState } from "react";
import {
  applyEncoderNow,
  getSettings,
  setAutorecord,
  setAutostart,
  setClipsDir,
  setCodec,
  setDriverIndex,
  setRole,
  unlockIt,
} from "../lib/ipc";
import { useAppStore } from "../stores/appStore";
import { useBackendEvent } from "./useBackendEvent";
import type { SettingsSnapshot } from "../types/dto";

const DRIVERS = ["auto", "nvidia", "intel", "amd", "cpu"];

interface UseSettingsForm {
  settings: SettingsSnapshot | null;
  restartState: "idle" | "restarting" | "done" | "error";
  restartError: string | null;
  actions: {
    setClipsDir: (path: string) => Promise<void>;
    setDriver: (driver: string) => Promise<void>;
    setCodec: (codec: string) => Promise<void>;
    setAutorecord: (enabled: boolean) => Promise<void>;
    setAutostart: (enabled: boolean) => Promise<void>;
    applyEncoderNow: () => Promise<void>;
    setRole: (role: string) => Promise<boolean>;
    unlockIt: (pin: string) => Promise<boolean>;
  };
}

/** Settings-domain hook: reads/writes project/app/adapters/ipc/router.py's settings commands. */
export function useSettingsForm(): UseSettingsForm {
  const settings = useAppStore((s) => s.settings);
  const [restartState, setRestartState] = useState<"idle" | "restarting" | "done" | "error">("idle");
  const [restartError, setRestartError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    void getSettings().then((s) => useAppStore.setState({ settings: s }));
  }, []);

  useBackendEvent("encoder_restart_started", () => setRestartState("restarting"));
  useBackendEvent("encoder_restart_finished", () => setRestartState("done"));
  useBackendEvent("encoder_restart_failed", (ev) => {
    setRestartState("error");
    setRestartError(ev.message);
  });

  useEffect(() => {
    if (restartState === "done" || restartState === "error") {
      const t = setTimeout(() => setRestartState("idle"), 3000);
      return () => clearTimeout(t);
    }
  }, [restartState]);

  return {
    settings,
    restartState,
    restartError,
    actions: {
      setClipsDir: async (path) => {
        await setClipsDir(path);
        refresh();
      },
      setDriver: async (driver) => {
        const index = DRIVERS.indexOf(driver);
        if (index >= 0) await setDriverIndex(index);
        refresh();
      },
      setCodec: async (codec) => {
        await setCodec(codec);
        refresh();
      },
      setAutorecord: async (enabled) => {
        await setAutorecord(enabled);
        refresh();
      },
      setAutostart: async (enabled) => {
        await setAutostart(enabled);
        refresh();
      },
      applyEncoderNow: async () => {
        await applyEncoderNow();
      },
      setRole: async (role) => {
        const { applied } = await setRole(role);
        if (applied) refresh();
        return applied;
      },
      unlockIt: async (pin) => {
        const { ok } = await unlockIt(pin);
        if (ok) refresh();
        return ok;
      },
    },
  };
}

export { DRIVERS };
