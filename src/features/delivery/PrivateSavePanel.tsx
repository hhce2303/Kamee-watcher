import { usePrivateSave } from "../../hooks/usePrivateSave";

const STATE_COLOR: Record<string, string> = {
  idle: "var(--text-dim)",
  working: "#60A5FA",
  saved: "var(--accent-ok)",
  error: "var(--accent-record)",
};

/**
 * Private OneDrive save (IT role) — exports the reel straight into the
 * resolved OneDrive folder and confirms, no share link. Sibling to
 * OutputPanel.tsx (Supervisor's share-link flow), kept as a separate
 * component/hook rather than modified in place — OutputPanel is also used by
 * SupervisorView and ITHealthChips, so this stays purely additive.
 *
 * FUTURE escalation to sharing: once IT needs to hand a link to a Supervisor,
 * add a "Compartir" action here that calls ensureFolderAndLink() (already
 * implemented, see OutputPanel) against `folder` below — additive, not a
 * rewrite of this panel.
 */
export default function PrivateSavePanel() {
  const { state, outputPath, progress, error, save, reset } = usePrivateSave();

  return (
    <div style={{ border: "1px solid var(--border-base)", borderRadius: "var(--r-md)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, height: 44, padding: "0 18px", borderBottom: "1px solid var(--border-base)" }}>
        <span style={{ color: "#60A5FA" }}>☁</span>
        <span style={{ color: "#60A5FA", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: "1.6px" }}>
          ONEDRIVE · PRIVADO
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ width: 5, height: 5, borderRadius: 3, background: STATE_COLOR[state] }} />
        <span style={{ color: STATE_COLOR[state], fontFamily: "var(--font-mono)", fontSize: 11 }}>{state.toUpperCase()}</span>
      </div>

      <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
        {state === "idle" && (
          <>
            <button type="button" onClick={save} style={primaryBtnStyle}>
              Guardar en OneDrive
            </button>
            <p style={{ color: "var(--text-dim)", fontSize: 12, margin: 0 }}>privado — sin enlace</p>
          </>
        )}
        {state === "working" && (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            Guardando… {Math.round(progress * 100)}%
          </p>
        )}
        {state === "saved" && (
          <>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-muted)", wordBreak: "break-all" }}>
              Guardado ✓ {outputPath}
            </div>
            <button type="button" onClick={reset} style={secondaryBtnStyle}>
              Reiniciar
            </button>
          </>
        )}
        {state === "error" && (
          <>
            <p style={{ color: "var(--accent-record)", fontSize: 13 }}>{error}</p>
            <button type="button" onClick={save} style={primaryBtnStyle}>
              Reintentar
            </button>
          </>
        )}
      </div>
    </div>
  );
}

const primaryBtnStyle = {
  height: 32,
  padding: "0 16px",
  borderRadius: "var(--r-sm)",
  border: "none",
  background: "var(--accent-primary)",
  color: "var(--bg-base)",
  fontSize: 13,
  fontWeight: 700,
  cursor: "pointer",
} as const;

const secondaryBtnStyle = {
  height: 30,
  padding: "0 14px",
  borderRadius: "var(--r-sm)",
  border: "1px solid var(--border-base)",
  background: "transparent",
  color: "var(--text-muted)",
  fontSize: 12,
  cursor: "pointer",
  alignSelf: "flex-start",
} as const;
