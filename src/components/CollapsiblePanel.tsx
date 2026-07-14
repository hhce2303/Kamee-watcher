import { useState, type ReactNode } from "react";

interface CollapsiblePanelProps {
  /** Which edge of the layout this panel hugs — controls where the toggle
   * button sits and which way its arrow points. */
  side: "left" | "right";
  label: string;
  icon?: string;
  /** Expanded width in px. */
  width?: number;
  defaultCollapsed?: boolean;
  children: ReactNode;
}

const COLLAPSED_WIDTH = 34;

/**
 * Collapsible side panel — lets flex siblings (e.g. the reel editor) reclaim
 * width for 16:9 playback when the user doesn't need this panel open.
 * Presentational only, no IPC awareness — collapse state is local UI state.
 */
export default function CollapsiblePanel({ side, label, icon, width = 280, defaultCollapsed = false, children }: CollapsiblePanelProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  if (collapsed) {
    return (
      <div
        style={{
          width: COLLAPSED_WIDTH,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 10,
          padding: "10px 0",
          borderRadius: "var(--r-md)",
          border: "1px solid var(--border-base)",
          background: "var(--bg-surface)",
        }}
      >
        <ToggleButton collapsed side={side} onClick={() => setCollapsed(false)} />
        <span
          style={{
            writingMode: "vertical-rl",
            color: "var(--text-muted)",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            letterSpacing: "1.2px",
            whiteSpace: "nowrap",
          }}
        >
          {icon ? `${icon} ` : ""}{label}
        </span>
      </div>
    );
  }

  return (
    <div style={{ width, flexShrink: 0, display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: side === "left" ? "flex-end" : "flex-start" }}>
        <ToggleButton collapsed={false} side={side} onClick={() => setCollapsed(true)} />
      </div>
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}>{children}</div>
    </div>
  );
}

function ToggleButton({ collapsed, side, onClick }: { collapsed: boolean; side: "left" | "right"; onClick: () => void }) {
  const pointsRight = side === "left" ? collapsed : !collapsed;
  return (
    <button
      type="button"
      onClick={onClick}
      title={collapsed ? "Expandir panel" : "Colapsar panel"}
      aria-label={collapsed ? "Expandir panel" : "Colapsar panel"}
      style={{
        width: 22,
        height: 22,
        flexShrink: 0,
        borderRadius: "var(--r-xs)",
        border: "1px solid var(--border-base)",
        background: "transparent",
        color: "var(--text-muted)",
        fontSize: 12,
        lineHeight: 1,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {pointsRight ? "›" : "‹"}
    </button>
  );
}
