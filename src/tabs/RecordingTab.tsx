import { useEffect, useState } from "react";
import { useIpc } from "../hooks/useIpc";
import { useTauriEvent } from "../hooks/useTauriEvent";
import type { RecordingState, MonitorDTO } from "../types/dto";

export default function RecordingTab() {
  const { send } = useIpc();
  const [state, setState]     = useState<RecordingState | null>(null);
  const [monitors, setMonitors] = useState<MonitorDTO[]>([]);
  const [busy, setBusy]       = useState(false);

  useEffect(() => {
    send<RecordingState>("get_recording_state").then(setState).catch(console.error);
    send<MonitorDTO[]>("get_monitors").then(setMonitors).catch(console.error);
  }, []);

  useTauriEvent<RecordingState>("RecordingStateChanged", (ev) => setState(ev));
  useTauriEvent<MonitorDTO[]>("MonitorsChanged",         (ev) => setMonitors(ev));

  async function handleToggleRecording() {
    if (!state) return;
    setBusy(true);
    try {
      if (state.is_recording) {
        await send("stop_recording", {});
      } else {
        await send("start_recording", {});
      }
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  }

  async function handleTriggerEvent() {
    try {
      await send("trigger_event", {});
    } catch (e) {
      console.error(e);
    }
  }

  async function handleToggleMonitor(fingerprint: string) {
    try {
      await send("toggle_monitor", { fingerprint });
    } catch (e) {
      console.error(e);
    }
  }

  if (!state) {
    return (
      <div className="placeholder-tab">
        <p>Connecting to backend…</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-7)" }}>
      {/* Status row */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-5)" }}>
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            background: state.is_recording ? "var(--accent-record)" : "var(--text-dim)",
            flexShrink: 0,
          }}
        />
        <span style={{ fontWeight: 600, fontSize: 15 }}>
          {state.is_recording
            ? `Recording — ${state.record_seconds}s · ${state.event_count} events`
            : "Idle"}
        </span>
        <button
          onClick={handleToggleRecording}
          disabled={busy}
          style={{
            marginLeft: "auto",
            padding: "6px 18px",
            borderRadius: "var(--r-sm)",
            border: "none",
            background: state.is_recording ? "var(--record-dim)" : "var(--primary-dim)",
            color: state.is_recording ? "var(--accent-record)" : "var(--accent-primary)",
            fontFamily: "var(--font-sans)",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {state.is_recording ? "Stop" : "Start"}
        </button>
        <button
          onClick={handleTriggerEvent}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--r-sm)",
            border: "1px solid var(--border-subtle)",
            background: "transparent",
            color: "var(--text-muted)",
            fontFamily: "var(--font-sans)",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          Trigger event
        </button>
      </div>

      {/* Monitor list */}
      {monitors.length > 0 && (
        <div>
          <p style={{ color: "var(--text-muted)", fontSize: 11, marginBottom: "var(--sp-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Monitors
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
            {monitors.map((m) => (
              <div
                key={m.fingerprint}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-4)",
                  padding: "var(--sp-3) var(--sp-4)",
                  background: "var(--bg-surface)",
                  borderRadius: "var(--r-md)",
                  border: m.selected ? "1px solid var(--accent-monitor)" : "1px solid var(--border-base)",
                }}
              >
                <span style={{ flex: 1 }}>
                  <span style={{ fontWeight: 500 }}>{m.name}</span>
                  <span style={{ color: "var(--text-dim)", marginLeft: "var(--sp-3)", fontSize: 12 }}>
                    {m.resolution}
                  </span>
                </span>
                <button
                  onClick={() => handleToggleMonitor(m.fingerprint)}
                  style={{
                    padding: "3px 10px",
                    borderRadius: "var(--r-xs)",
                    border: "none",
                    background: m.selected ? "var(--monitor-dim)" : "var(--bg-elevated)",
                    color: m.selected ? "var(--accent-monitor)" : "var(--text-muted)",
                    fontFamily: "var(--font-sans)",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {m.selected ? "On" : "Off"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
