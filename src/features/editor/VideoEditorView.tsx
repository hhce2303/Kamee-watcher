import { useState } from "react";
import { useEditorTimeline } from "../../hooks/useEditorTimeline";
import EditorTimeline from "./EditorTimeline";
import EditorTransport from "./EditorTransport";
import ExportDialog from "./ExportDialog";

interface VideoEditorViewProps {
  defaultOutputPath: string;
}

/** Evidence-reel editor workspace — port of qml/VideoEditor.qml. */
export default function VideoEditorView({ defaultOutputPath }: VideoEditorViewProps) {
  const { entries, totalDuration, actions } = useEditorTimeline();
  const [selected, setSelected] = useState<number | null>(null);

  const selectedEntry = selected !== null ? (entries[selected] ?? null) : null;

  function handleRemove(index: number) {
    void actions.remove(index);
    if (selected === index) setSelected(null);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", border: "1px solid var(--border-base)", borderRadius: "var(--r-md)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, height: 40, padding: "0 14px", borderBottom: "1px solid var(--border-base)", background: "var(--bg-elevated)" }}>
        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "1.2px" }}>REEL</span>
        <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
          {entries.length} clip{entries.length !== 1 ? "s" : ""} · {totalDuration.toFixed(1)}s
        </span>
        <div style={{ flex: 1 }} />
        <button type="button" onClick={() => void actions.clear()} style={clearBtnStyle}>Vaciar</button>
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ width: 260, flexShrink: 0, overflow: "auto", padding: 10, borderRight: "1px solid var(--border-base)" }}>
          <EditorTimeline entries={entries} selected={selected} onSelect={setSelected} onRemove={handleRemove} onMove={actions.move} />
        </div>
        <div style={{ flex: 1, padding: 14, overflow: "auto" }}>
          <EditorTransport
            entry={selectedEntry}
            onTrim={(inS, outS) => selected !== null && void actions.trim(selected, inS, outS)}
          />
        </div>
      </div>

      <ExportDialog defaultOutputPath={defaultOutputPath} />
    </div>
  );
}

const clearBtnStyle = {
  height: 26,
  padding: "0 10px",
  borderRadius: "var(--r-sm)",
  border: "1px solid var(--border-base)",
  background: "transparent",
  color: "var(--text-muted)",
  fontSize: 12,
  cursor: "pointer",
} as const;
