import type { ClipEntryDTO } from "../../types/dto";

interface EditorTimelineProps {
  entries: ClipEntryDTO[];
  selected: number | null;
  onSelect: (index: number) => void;
  onRemove: (index: number) => void;
  onMove: (src: number, dst: number) => void;
}

/** Reel clip list — port of qml/VideoEditor.qml's timeline strip (reorder via
 * up/down instead of drag, which is simpler and just as usable for a reel
 * that's edited a few clips at a time). */
export default function EditorTimeline({ entries, selected, onSelect, onRemove, onMove }: EditorTimelineProps) {
  if (entries.length === 0) {
    return <p style={{ color: "var(--text-dim)", fontSize: 13, padding: 16 }}>Sin clips en la línea de tiempo.</p>;
  }

  return (
    <div role="listbox" aria-label="Clips en la línea de tiempo" style={{ display: "flex", flexDirection: "column", gap: 6, overflow: "auto" }}>
      {entries.map((entry, i) => {
        const duration = entry.out_point_s - entry.in_point_s;
        return (
          <div
            key={`${entry.source_path}-${i}`}
            role="option"
            aria-selected={selected === i}
            tabIndex={0}
            onClick={() => onSelect(i)}
            onKeyDown={(e) => { if (e.key === "Enter") onSelect(i); }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 10px",
              borderRadius: "var(--r-sm)",
              background: selected === i ? "var(--primary-dim)" : "var(--bg-surface)",
              border: `1px solid ${selected === i ? "var(--accent-primary)" : "var(--border-base)"}`,
              cursor: "pointer",
            }}
          >
            <span aria-hidden="true" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 11, width: 20 }}>{i + 1}</span>
            <span style={{ flex: 1, minWidth: 0, color: "var(--text-primary)", fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {entry.source_path.split(/[/\\]/).pop()}
            </span>
            <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{duration.toFixed(1)}s</span>
            <button type="button" aria-label="Mover arriba" onClick={(e) => { e.stopPropagation(); onMove(i, i - 1); }} disabled={i === 0} style={iconBtnStyle}>↑</button>
            <button type="button" aria-label="Mover abajo" onClick={(e) => { e.stopPropagation(); onMove(i, i + 1); }} disabled={i === entries.length - 1} style={iconBtnStyle}>↓</button>
            <button type="button" aria-label="Quitar clip" onClick={(e) => { e.stopPropagation(); onRemove(i); }} style={{ ...iconBtnStyle, color: "var(--accent-record)" }}>✕</button>
          </div>
        );
      })}
    </div>
  );
}

const iconBtnStyle = {
  width: 22,
  height: 22,
  border: "none",
  background: "transparent",
  color: "var(--text-muted)",
  cursor: "pointer",
  fontSize: 12,
} as const;
