export type Range = "1h" | "6h" | "24h" | "7d";

export const RANGE_LABELS: Record<Range, string> = { "1h": "1 h", "6h": "6 h", "24h": "24 h", "7d": "7 days" };

interface AnalyticsFiltersProps {
  range: Range;
  onRangeChange: (r: Range) => void;
  monitorIdx: number | null;
  onMonitorChange: (idx: number | null) => void;
  loading: boolean;
  onRefresh: () => void;
}

/** Time-range + monitor filter row, plus the loading/refresh indicator. */
export default function AnalyticsFilters({
  range,
  onRangeChange,
  monitorIdx,
  onMonitorChange,
  loading,
  onRefresh,
}: AnalyticsFiltersProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-4)", flexWrap: "wrap" }}>
      {/* Time range */}
      <div style={{ display: "flex", gap: "var(--sp-2)" }}>
        {(Object.keys(RANGE_LABELS) as Range[]).map((r) => (
          <button
            key={r}
            onClick={() => onRangeChange(r)}
            style={{
              padding: "4px 12px",
              borderRadius: "var(--r-sm)",
              border: "1px solid " + (range === r ? "var(--accent-primary)" : "var(--border-subtle)"),
              background: range === r ? "var(--primary-dim)" : "transparent",
              color: range === r ? "var(--accent-primary)" : "var(--text-muted)",
              fontSize: 12,
              fontWeight: 600,
              fontFamily: "var(--font-sans)",
              cursor: "pointer",
            }}
          >
            {RANGE_LABELS[r]}
          </button>
        ))}
      </div>

      {/* Monitor filter */}
      <select
        value={monitorIdx ?? ""}
        onChange={(e) => onMonitorChange(e.target.value === "" ? null : Number(e.target.value))}
        style={{
          padding: "4px 8px",
          borderRadius: "var(--r-sm)",
          border: "1px solid var(--border-subtle)",
          background: "var(--bg-elevated)",
          color: "var(--text-primary)",
          fontFamily: "var(--font-sans)",
          fontSize: 12,
        }}
      >
        <option value="">All monitors</option>
        <option value="0">Monitor 0</option>
        <option value="1">Monitor 1</option>
        <option value="2">Monitor 2</option>
        <option value="3">Monitor 3</option>
      </select>

      {loading && (
        <span style={{ color: "var(--text-dim)", fontSize: 12, marginLeft: "auto" }}>Refreshing…</span>
      )}
      {!loading && (
        <button
          onClick={onRefresh}
          style={{
            marginLeft: "auto",
            padding: "4px 10px",
            borderRadius: "var(--r-sm)",
            border: "1px solid var(--border-subtle)",
            background: "transparent",
            color: "var(--text-muted)",
            fontSize: 12,
            fontFamily: "var(--font-sans)",
            cursor: "pointer",
          }}
        >
          Refresh
        </button>
      )}
    </div>
  );
}
