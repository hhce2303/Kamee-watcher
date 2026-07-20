import { useEffect, useState } from "react";
import { useLiveAnalytics } from "../hooks/useLiveAnalytics";
import AnalyticsFilters, { type Range } from "./analytics/AnalyticsFilters";
import CountsChart from "./analytics/CountsChart";
import DwellTable from "./analytics/DwellTable";
import ZonePanel from "./analytics/ZonePanel";

// ── Time-range helpers ────────────────────────────────────────────────────────

const RANGE_MS: Record<Range, number> = {
  "1h":  1 * 3600_000,
  "6h":  6 * 3600_000,
  "24h": 24 * 3600_000,
  "7d":  7 * 86400_000,
};

function rangeWindow(r: Range): { since: string; until: string } {
  const now = Date.now();
  return {
    since: new Date(now - RANGE_MS[r]).toISOString(),
    until: new Date(now).toISOString(),
  };
}

// ── AnalyticsTab (main) ───────────────────────────────────────────────────────

const PANEL_STYLE: React.CSSProperties = {
  background: "var(--bg-surface)",
  border: "1px solid var(--border-base)",
  borderRadius: "var(--r-lg)",
  padding: "var(--sp-5)",
  display: "flex",
  flexDirection: "column",
  gap: "var(--sp-4)",
};

const SECTION_LABEL: React.CSSProperties = {
  color: "var(--text-muted)",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  fontWeight: 600,
  marginBottom: 2,
};

export default function AnalyticsTab() {
  const [range, setRange]           = useState<Range>("1h");
  const [monitorIdx, setMonitorIdx] = useState<number | null>(null);
  const [zoneName, setZoneName]     = useState("");
  const [zoneInput, setZoneInput]   = useState("");
  const [window_, setWindow]        = useState(rangeWindow("1h"));

  // Rebuild the time window whenever the range selection changes.
  useEffect(() => { setWindow(rangeWindow(range)); }, [range]);

  const filters = {
    since:        window_.since,
    until:        window_.until,
    monitorIndex: monitorIdx,
    zoneName,
  };

  const { counts, dwell, zoneEvents, loading, error, refresh } = useLiveAnalytics(filters);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-5)" }}>

      <AnalyticsFilters
        range={range}
        onRangeChange={setRange}
        monitorIdx={monitorIdx}
        onMonitorChange={setMonitorIdx}
        loading={loading}
        onRefresh={refresh}
      />

      {error && (
        <div style={{
          padding: "var(--sp-3) var(--sp-4)",
          borderRadius: "var(--r-md)",
          background: "rgba(244,63,94,0.08)",
          color: "var(--accent-record)",
          fontSize: 13,
          border: "1px solid rgba(244,63,94,0.2)",
        }}>
          {error}
        </div>
      )}

      {/* ── Counts chart ── */}
      <div style={PANEL_STYLE}>
        <p style={SECTION_LABEL}>Detections by class</p>
        <CountsChart counts={counts} />
        {counts.length > 0 && (
          <p style={{ color: "var(--text-dim)", fontSize: 11, marginTop: 2 }}>
            Total: {counts.reduce((s, c) => s + c.count, 0)} events · {counts.length} class{counts.length !== 1 ? "es" : ""}
          </p>
        )}
      </div>

      {/* ── Dwell table ── */}
      <div style={PANEL_STYLE}>
        <p style={SECTION_LABEL}>Dwell times by track</p>
        <DwellTable rows={dwell} />
      </div>

      {/* ── Zone panel ── */}
      <div style={PANEL_STYLE}>
        <p style={SECTION_LABEL}>Zone events</p>
        <div style={{ display: "flex", gap: "var(--sp-3)", alignItems: "center" }}>
          <input
            type="text"
            placeholder="Zone name (e.g. entrance)"
            value={zoneInput}
            onChange={(e) => setZoneInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") setZoneName(zoneInput.trim()); }}
            style={{
              flex: 1,
              padding: "5px 10px",
              borderRadius: "var(--r-sm)",
              border: "1px solid var(--border-subtle)",
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              fontFamily: "var(--font-sans)",
              fontSize: 13,
            }}
          />
          <button
            onClick={() => setZoneName(zoneInput.trim())}
            style={{
              padding: "5px 14px",
              borderRadius: "var(--r-sm)",
              border: "none",
              background: "var(--primary-dim)",
              color: "var(--accent-primary)",
              fontFamily: "var(--font-sans)",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Query
          </button>
        </div>
        {zoneName ? (
          <>
            <p style={{ color: "var(--text-dim)", fontSize: 12 }}>
              Zone: <span style={{ color: "var(--text-primary)" }}>{zoneName}</span>
              {" · "}{zoneEvents.length} event{zoneEvents.length !== 1 ? "s" : ""}
            </p>
            <ZonePanel events={zoneEvents} />
          </>
        ) : (
          <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", margin: "16px 0" }}>
            Enter a zone name to view events.
          </p>
        )}
      </div>

    </div>
  );
}
