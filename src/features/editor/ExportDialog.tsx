import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useEditorExport } from "../../hooks/useEditorExport";

interface ExportDialogProps {
  defaultOutputPath: string;
}

/** Export trigger + progress — port of VideoEditor.qml's export flow. */
export default function ExportDialog({ defaultOutputPath }: ExportDialogProps) {
  const { state, progress, outputPath, error, start } = useEditorExport();
  const [path, setPath] = useState(defaultOutputPath);

  async function pickPath() {
    const chosen = await save({ defaultPath: path, filters: [{ name: "MP4", extensions: ["mp4"] }] });
    if (chosen) setPath(chosen);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 14, borderTop: "1px solid var(--border-base)" }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={path} onChange={(e) => setPath(e.target.value)} style={pathInputStyle} />
        <button type="button" onClick={pickPath} style={secondaryBtnStyle}>Elegir…</button>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button
          type="button"
          disabled={state === "exporting" || !path}
          onClick={() => void start(path)}
          style={primaryBtnStyle}
        >
          {state === "exporting" ? `Exportando… ${(progress * 100).toFixed(0)}%` : "Exportar reel"}
        </button>
        {state === "done" && outputPath && <span style={{ color: "var(--accent-ok)", fontSize: 13 }}>✓ {outputPath}</span>}
        {state === "error" && error && <span style={{ color: "var(--accent-record)", fontSize: 13 }}>{error}</span>}
      </div>
    </div>
  );
}

const pathInputStyle = {
  flex: 1,
  height: 32,
  padding: "0 10px",
  borderRadius: "var(--r-sm)",
  border: "1px solid var(--border-base)",
  background: "var(--bg-base)",
  color: "var(--text-primary)",
  fontFamily: "var(--font-mono)",
  fontSize: 12,
} as const;

const primaryBtnStyle = {
  height: 34,
  padding: "0 18px",
  borderRadius: "var(--r-sm)",
  border: "none",
  background: "var(--accent-primary)",
  color: "var(--bg-base)",
  fontSize: 13,
  fontWeight: 700,
  cursor: "pointer",
} as const;

const secondaryBtnStyle = {
  height: 32,
  padding: "0 14px",
  borderRadius: "var(--r-sm)",
  border: "1px solid var(--border-base)",
  background: "var(--bg-surface)",
  color: "var(--text-primary)",
  fontSize: 13,
  cursor: "pointer",
} as const;
