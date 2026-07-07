import { useRecording } from "../hooks/useRecording";
import { useAppStore } from "../stores/appStore";
import LogTicker from "./LogTicker";

function fmtTime(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

const dividerStyle = { width: 1, height: 12, background: "var(--border-base)" };
const cellStyle = { color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 };

/** Bottom statusbar — port of qml/Statusbar.qml. */
export default function Statusbar() {
  const { state } = useRecording();
  const ipcConnected = useAppStore((s) => s.ipcConnected);
  const clipsDir = useAppStore((s) => s.settings?.clips_dir ?? "C:/WatcherData");

  return (
    <div
      style={{
        height: 24,
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "0 16px",
        background: "var(--bg-elevated)",
        borderTop: "1px solid var(--border-base)",
        flexShrink: 0,
      }}
    >
      {state?.is_recording && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 5, height: 5, borderRadius: 3, background: "var(--accent-record)" }} />
            <span style={{ color: "var(--accent-record)", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, letterSpacing: "1px" }}>
              GRABANDO
            </span>
            <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
              {fmtTime(state.record_seconds)}
            </span>
          </div>
          <div style={dividerStyle} />
          <span style={cellStyle}>{state.event_count} eventos</span>
          <div style={dividerStyle} />
        </>
      )}
      <span style={cellStyle}>buffer 2:00 / 60 seg</span>
      <div style={dividerStyle} />
      <span style={cellStyle}>{clipsDir}</span>

      <div style={dividerStyle} />
      <div className="log-ticker-slot">
        <LogTicker />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            width: 4,
            height: 4,
            borderRadius: 2,
            background: ipcConnected ? "var(--accent-ok)" : "var(--accent-record)",
          }}
        />
        <span
          style={{
            color: ipcConnected ? "var(--accent-ok)" : "var(--accent-record)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            letterSpacing: "0.8px",
          }}
        >
          {ipcConnected ? "SISTEMA OK" : "SIN CONEXIÓN"}
        </span>
      </div>
    </div>
  );
}
