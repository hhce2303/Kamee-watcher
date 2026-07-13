import type { MonitorDTO } from "../../types/dto";

interface MonitorSelectorProps {
  monitors: MonitorDTO[];
  onToggle: (fingerprint: string) => void;
  showHeader?: boolean;
}

/** Reusable screen-selection list — port of qml/MonitorSelector.qml. */
export default function MonitorSelector({ monitors, onToggle, showHeader = true }: MonitorSelectorProps) {
  const activeCount = monitors.filter((m) => m.selected).length;

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {showHeader && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            height: 44,
            borderBottom: "1px solid var(--border-base)",
            padding: "0 16px 0 16px",
          }}
        >
          <span style={{ color: "var(--text-muted)", fontSize: 10, fontWeight: 700, letterSpacing: "1.4px" }}>
            PANTALLAS
          </span>
          <div style={{ flex: 1 }} />
          <span
            style={{
              padding: "2px 6px",
              borderRadius: "var(--r-pill)",
              background: "var(--primary-dim)",
              color: "var(--accent-primary)",
              fontFamily: "var(--font-mono)",
              fontSize: 9,
              fontWeight: 700,
            }}
          >
            {activeCount}/{monitors.length}
          </span>
        </div>
      )}

      {monitors.length === 0 && (
        <div style={{ padding: 24, textAlign: "center", color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
          Sin pantallas detectadas
        </div>
      )}

      {monitors.map((m) => (
        <button
          key={m.fingerprint}
          type="button"
          role="checkbox"
          aria-checked={m.selected}
          aria-label={`${m.name} (${m.resolution})`}
          onClick={() => onToggle(m.fingerprint)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            height: 58,
            padding: "0 14px",
            border: "none",
            borderLeft: `3px solid ${m.selected ? "var(--accent-monitor)" : "transparent"}`,
            borderBottom: "1px solid var(--border-base)",
            background: m.selected ? "rgba(129, 140, 248, 0.06)" : "transparent",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <span
            aria-hidden="true"
            style={{
              width: 18,
              height: 18,
              borderRadius: 4,
              flexShrink: 0,
              background: m.selected ? "var(--accent-monitor)" : "transparent",
              border: `1.5px solid ${m.selected ? "var(--accent-monitor)" : "var(--border-subtle)"}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--bg-base)",
              fontSize: 10,
              fontWeight: 700,
            }}
          >
            {m.selected ? "✓" : ""}
          </span>
          <span style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: m.selected ? "var(--text-primary)" : "var(--text-muted)", fontSize: 12, fontWeight: 700 }}>
              {m.name}
            </div>
            <div style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 10 }}>{m.resolution}</div>
          </span>
          <span
            style={{
              color: m.selected ? "var(--accent-monitor)" : "var(--border-subtle)",
              fontFamily: "var(--font-mono)",
              fontSize: 22,
              fontWeight: 700,
            }}
          >
            {String(m.index + 1).padStart(2, "0")}
          </span>
        </button>
      ))}
    </div>
  );
}
