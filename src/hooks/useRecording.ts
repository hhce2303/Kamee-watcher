import { useCallback, useEffect, useState } from "react";
import {
  getMonitors,
  getRecordingState,
  startRecording,
  stopRecording,
  toggleMonitor,
  triggerEvent,
} from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";
import { useTauriEvent } from "./useTauriEvent";
import type { MonitorDTO, RecordingState } from "../types/dto";

interface UseRecording {
  state: RecordingState | null;
  monitors: MonitorDTO[];
  busy: boolean;
  error: string | null;
  actions: {
    toggleRecording: () => Promise<void>;
    markEvent: () => Promise<boolean>;
    toggleMonitor: (fingerprint: string) => Promise<void>;
  };
}

/** Recording-domain hook: snapshot on mount + push updates from the bus. */
export function useRecording(): UseRecording {
  const [state, setState] = useState<RecordingState | null>(null);
  const [monitors, setMonitors] = useState<MonitorDTO[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    getRecordingState().then(setState).catch((e) => setError(String(e)));
    getMonitors().then(setMonitors).catch((e) => setError(String(e)));
  }, []);

  useEffect(refresh, [refresh]);
  useTauriEvent("ipc_connected", refresh);

  useBackendEvent("recording_state_changed", (ev) => setState(ev.state));
  useBackendEvent("monitors_changed", (ev) => setMonitors(ev.monitors));
  useBackendEvent("recording_failed", (ev) => setError(ev.message));

  const toggleRecording = useCallback(async () => {
    if (state === null) return;
    setBusy(true);
    setError(null);
    try {
      const next = state.is_recording ? await stopRecording() : await startRecording();
      setState(next);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [state]);

  const markEvent = useCallback(async () => {
    try {
      const { accepted } = await triggerEvent();
      return accepted;
    } catch (e) {
      setError(String(e));
      return false;
    }
  }, []);

  const doToggleMonitor = useCallback(async (fingerprint: string) => {
    try {
      setMonitors(await toggleMonitor(fingerprint));
    } catch (e) {
      setError(String(e));
    }
  }, []);

  return {
    state,
    monitors,
    busy,
    error,
    actions: { toggleRecording, markEvent, toggleMonitor: doToggleMonitor },
  };
}
