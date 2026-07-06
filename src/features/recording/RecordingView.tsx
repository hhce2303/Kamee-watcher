import { useEffect, useState } from "react";
import { useRecording } from "../../hooks/useRecording";
import { useAppStore } from "../../stores/appStore";
import MonitorSelector from "./MonitorSelector";
import MonitorTile from "./MonitorTile";
import BufferTimeline, { type EventMarker } from "./BufferTimeline";
import MarkEventButton from "./MarkEventButton";
import PreRollOverlay from "./PreRollOverlay";
import AnnotationModal from "./AnnotationModal";
import ITInboxPanel from "../it/ITInboxPanel";

type Flow = "idle" | "preroll" | "annotate";

function fmtTimecode(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

/** Grabación tab — port of qml/Main.qml's tab 0 (recording + preview + events). */
export default function RecordingView() {
  const { state, monitors, busy, error, actions } = useRecording();
  const [flow, setFlow] = useState<Flow>("idle");
  const [markers, setMarkers] = useState<EventMarker[]>([]);
  const [inboxOpen, setInboxOpen] = useState(false);
  const isIt = useAppStore((s) => s.settings?.role) === "it";

  useEffect(() => {
    if (!isIt) return;
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey && e.key.toLowerCase() === "i") {
        e.preventDefault();
        setInboxOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isIt]);

  if (!state) {
    return (
      <div className="placeholder-tab">
        <p>Connecting to backend…</p>
      </div>
    );
  }

  async function handleMarkEvent() {
    const accepted = await actions.markEvent();
    if (accepted) setFlow("preroll");
  }

  function handleAnnotationSaved(tag: string) {
    setMarkers((prev) => [...prev, { sec: state!.record_seconds, tag }]);
    setFlow("idle");
  }

  return (
    <div style={{ display: "flex", gap: "var(--sp-6)", height: "100%" }}>
      <aside style={{ width: 260, flexShrink: 0, background: "var(--bg-surface)", borderRadius: "var(--r-md)", border: "1px solid var(--border-base)" }}>
        <MonitorSelector monitors={monitors} onToggle={actions.toggleMonitor} />
      </aside>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-5)" }}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              background: state.is_recording ? "var(--accent-record)" : "var(--text-dim)",
            }}
          />
          <span style={{ fontWeight: 600, fontSize: 15 }}>
            {state.is_recording ? `Grabando — ${fmtTimecode(state.record_seconds)}` : "Inactivo"}
          </span>
          <div style={{ flex: 1 }} />
          <button
            type="button"
            onClick={actions.toggleRecording}
            disabled={busy}
            style={{
              padding: "6px 18px",
              borderRadius: "var(--r-sm)",
              border: "none",
              background: state.is_recording ? "var(--record-dim)" : "var(--primary-dim)",
              color: state.is_recording ? "var(--accent-record)" : "var(--accent-primary)",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {state.is_recording ? "Detener" : "Iniciar"}
          </button>
          <MarkEventButton onClick={handleMarkEvent} disabled={!state.is_recording} />
        </div>

        {error && <p style={{ color: "var(--accent-record)", fontSize: 12 }}>{error}</p>}

        <div
          style={{
            flex: 1,
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(monitors.length, 2) || 1}, 1fr)`,
            gap: "var(--sp-4)",
            alignContent: "start",
            overflow: "auto",
          }}
        >
          {monitors.map((m) => (
            <MonitorTile key={m.fingerprint} monitor={m} isRecording={state.is_recording} />
          ))}
        </div>

        <BufferTimeline recordSec={state.record_seconds} eventMarkers={markers} />
      </div>

      {isIt && inboxOpen && (
        <aside style={{ width: 320, flexShrink: 0 }}>
          <ITInboxPanel />
        </aside>
      )}

      {flow === "preroll" && (
        <PreRollOverlay onFinished={() => setFlow("annotate")} onCancelled={() => setFlow("idle")} />
      )}
      {flow === "annotate" && (
        <AnnotationModal
          eventTimecode={fmtTimecode(state.record_seconds)}
          onSaved={handleAnnotationSaved}
          onSkipped={() => setFlow("idle")}
        />
      )}
    </div>
  );
}
