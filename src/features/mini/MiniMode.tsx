import { getCurrentWindow } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { useRecording } from "../../hooks/useRecording";

const BAR_COUNT = 30;
const WINDOW_SEC = 120;

function fmtTime(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

async function expandToMain() {
  const main = await WebviewWindow.getByLabel("main");
  await main?.show();
  await main?.setFocus();
  await getCurrentWindow().hide();
}

/**
 * Floating always-on-top mini widget — port of qml/MiniMode.qml. Rendered by
 * App.tsx when the URL has `?window=mini` (its own Tauri window, declared in
 * tauri.conf.json). Each window is an independent JS context that subscribes
 * to the same backend events directly — no cross-window state sharing needed.
 */
export default function MiniMode() {
  const { state, actions } = useRecording();
  const recordSec = state?.record_seconds ?? 0;
  const filledSec = Math.min(recordSec, WINDOW_SEC);
  const barsFilled = Math.floor((filledSec / WINDOW_SEC) * BAR_COUNT);

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        borderRadius: "var(--r-md)",
        background: "rgba(13, 18, 32, 0.94)",
        border: "1px solid var(--border-subtle)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* role="presentation": this is a window drag handle (like a title bar),
          not a control itself — the expand/close buttons inside are real,
          independently focusable buttons. */}
      <div
        role="presentation"
        onMouseDown={() => void getCurrentWindow().startDragging()}
        style={{ display: "flex", alignItems: "center", height: 28, padding: "0 12px 0 12px", background: "var(--bg-base)", borderBottom: "1px solid var(--border-base)", cursor: "move" }}
      >
        <span style={{ width: 5, height: 5, borderRadius: 3, background: "var(--accent-record)" }} />
        <span style={{ marginLeft: 6, color: "var(--text-primary)", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: "1.6px" }}>
          THE WATCHER · MINI
        </span>
        <div style={{ flex: 1 }} />
        <button type="button" aria-label="Expandir a ventana principal" onClick={() => void expandToMain()} style={miniIconBtnStyle}>⤢</button>
        <button type="button" aria-label="Ocultar mini-modo" onClick={() => void getCurrentWindow().hide()} style={miniIconBtnStyle}>✕</button>
      </div>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12, padding: 14 }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <span style={{ padding: "0 9px", height: 18, display: "flex", alignItems: "center", borderRadius: "var(--r-xs)", background: "var(--record-dim)", border: "1px solid var(--accent-record)", color: "var(--accent-record)", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600 }}>
            ● LIVE · REC
          </span>
          <div style={{ flex: 1 }} />
          <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 700 }}>{fmtTime(recordSec)}</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "1.2px" }}>BUFFER</span>
            <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 10 }}>2:00</span>
          </div>
          <div style={{ position: "relative", height: 14, display: "flex", gap: 1 }}>
            {Array.from({ length: BAR_COUNT }, (_, i) => (
              <div key={i} style={{ flex: 1, borderRadius: 1, background: i < barsFilled ? "var(--accent-primary)" : "var(--border-base)", opacity: i < barsFilled ? (i / BAR_COUNT) * 0.5 + 0.5 : 1 }} />
            ))}
            <div style={{ position: "absolute", right: 0, top: -2, bottom: -2, width: 2, background: "var(--accent-record)" }} />
          </div>
        </div>

        <button
          type="button"
          onClick={() => void actions.markEvent()}
          style={{ height: 38, borderRadius: "var(--r-sm)", border: "none", background: "var(--accent-primary)", color: "var(--bg-base)", fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 700, letterSpacing: "1px", cursor: "pointer" }}
        >
          📍 MARCAR EVENTO
        </button>

        <div style={{ height: 1, background: "var(--border-base)" }} />

        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "1.2px" }}>EVENTOS HOY</span>
          <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 600 }}>{state?.event_count ?? 0}</span>
        </div>
      </div>
    </div>
  );
}

const miniIconBtnStyle = {
  width: 18,
  height: 18,
  marginLeft: 4,
  border: "none",
  background: "transparent",
  color: "var(--text-muted)",
  fontSize: 12,
  cursor: "pointer",
  borderRadius: 3,
} as const;
