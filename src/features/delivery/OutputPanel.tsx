import { useState } from "react";
import { useOutputPanel } from "../../hooks/useOutputPanel";

const STATE_COLOR: Record<string, string> = {
  idle: "var(--text-dim)",
  working: "var(--accent-cloud)",
  linked: "var(--accent-ok)",
  error: "var(--accent-record)",
};

/** OneDrive delivery panel — port of qml/OutputPanel.qml. One click runs the
 * whole real flow: find/create the destination folder → mint a share link. */
export default function OutputPanel() {
  const { state, folder, link, error, save, reset } = useOutputPanel();
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div style={{ border: "1px solid var(--border-base)", borderRadius: "var(--r-md)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, height: 44, padding: "0 18px", borderBottom: "1px solid var(--border-base)" }}>
        <span style={{ color: "var(--accent-cloud)" }}>☁</span>
        <span style={{ color: "var(--accent-cloud)", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: "1.6px" }}>
          ONEDRIVE · ENTREGA
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ width: 5, height: 5, borderRadius: 3, background: STATE_COLOR[state] }} />
        <span style={{ color: STATE_COLOR[state], fontFamily: "var(--font-mono)", fontSize: 11 }}>{state.toUpperCase()}</span>
      </div>

      <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
        {state === "idle" && (
          <button type="button" onClick={save} style={primaryBtnStyle}>
            Generar carpeta y enlace
          </button>
        )}
        {state === "working" && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Buscando/creando carpeta…</p>}
        {state === "linked" && (
          <>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-muted)" }}>{folder}</div>
            <div style={{ display: "flex", gap: 8 }}>
              <input readOnly value={link} style={{ flex: 1, height: 32, padding: "0 10px", borderRadius: "var(--r-sm)", border: "1px solid var(--border-base)", background: "var(--bg-base)", color: "var(--text-primary)", fontFamily: "var(--font-mono)", fontSize: 12 }} />
              <button type="button" onClick={handleCopy} style={primaryBtnStyle}>
                {copied ? "Copiado ✓" : "Copiar"}
              </button>
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
