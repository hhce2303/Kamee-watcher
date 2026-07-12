import { useEffect, useRef, useState } from "react";
import { useLiveAnalytics } from "../hooks/useLiveAnalytics";
import type { CountByClass, DwellRecord } from "../types/dto";
import type { AnalyticEventRaw } from "../hooks/useLiveAnalytics";

// ── Time-range helpers ────────────────────────────────────────────────────────

type Range = "1h" | "6h" | "24h" | "7d";
const RANGE_LABELS: Record<Range, string> = { "1h": "1 h", "6h": "6 h", "24h": "24 h", "7d": "7 days" };
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

// ── CountsChart ───────────────────────────────────────────────────────────────

const BAR_COLORS = [
  "#38bdf8", "#818cf8", "#34d399", "#facc15",
  "#fb923c", "#f472b6", "#a78bfa", "#4ade80",
];

function CountsChart({ counts }: { counts: CountByClass[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const W   = canvas.clientWidth;
    const H   = canvas.clientHeight;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, W, H);

    // Canvas 2D `font` does not resolve CSS custom properties — read the
    // real font-family value once so the chart doesn't silently fall back
    // to the browser default.
    const fontFamily =
      getComputedStyle(document.documentElement).getPropertyValue("--font-sans").trim() ||
      "sans-serif";

    if (counts.length === 0) {
      ctx.fillStyle = "#475569";
      ctx.font      = `13px ${fontFamily}`;
      ctx.textAlign = "center";
      ctx.fillText("No detections in this window", W / 2, H / 2);
      return;
    }

    const PAD_LEFT = 40, PAD_BOTTOM = 28, PAD_TOP = 12, PAD_RIGHT = 12;
    const chartW = W - PAD_LEFT - PAD_RIGHT;
    const chartH = H - PAD_TOP - PAD_BOTTOM;

    const maxCount = Math.max(...counts.map((c) => c.count));
    const barW     = Math.max(4, Math.floor(chartW / counts.length) - 6);

    // Y-axis labels
    const steps = 4;
    ctx.fillStyle = "#64748b";
    ctx.font      = `11px ${fontFamily}`;
    ctx.textAlign = "right";
    for (let i = 0; i <= steps; i++) {
      const val = Math.round((maxCount / steps) * i);
      const y   = PAD_TOP + chartH - (i / steps) * chartH;
      ctx.fillText(String(val), PAD_LEFT - 6, y + 4);
      ctx.strokeStyle = "#1e293b";
      ctx.lineWidth   = 1;
      ctx.beginPath();
      ctx.moveTo(PAD_LEFT, y);
      ctx.lineTo(PAD_LEFT + chartW, y);
      ctx.stroke();
    }

    // Bars + labels
    counts.forEach((c, i) => {
      const barH = maxCount > 0 ? (c.count / maxCount) * chartH : 0;
      const x    = PAD_LEFT + i * (chartW / counts.length) + (chartW / counts.length - barW) / 2;
      const y    = PAD_TOP + chartH - barH;

      ctx.fillStyle = BAR_COLORS[i % BAR_COLORS.length];
      const r = Math.min(4, barW / 2);
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + barW - r, y);
      ctx.quadraticCurveTo(x + barW, y, x + barW, y + r);
      ctx.lineTo(x + barW, y + barH);
      ctx.lineTo(x, y + barH);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.closePath();
      ctx.fill();

      // Count label on top of bar
      if (barH > 16) {
        ctx.fillStyle  = "rgba(0,0,0,0.6)";
        ctx.font       = `bold 11px ${fontFamily}`;
        ctx.textAlign  = "center";
        ctx.fillText(String(c.count), x + barW / 2, y + 14);
      }

      // Class label below bar
      ctx.fillStyle  = "#94a3b8";
      ctx.font       = `11px ${fontFamily}`;
      ctx.textAlign  = "center";
      ctx.fillText(
        c.class_name.length > 8 ? c.class_name.slice(0, 7) + "…" : c.class_name,
        x + barW / 2,
        PAD_TOP + chartH + 16,
      );
    });
  }, [counts]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: 180, display: "block" }}
    />
  );
}

// ── DwellTable ────────────────────────────────────────────────────────────────

function fmt(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function fmtSecs(s: number): string {
  if (s < 60)  return `${s.toFixed(1)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

function DwellTable({ rows }: { rows: DwellRecord[] }) {
  if (rows.length === 0) {
    return <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", margin: "24px 0" }}>No tracked objects in this window.</p>;
  }
  const sorted = [...rows].sort((a, b) => b.total_seconds - a.total_seconds);
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ color: "var(--text-muted)", textTransform: "uppercase", fontSize: 11, letterSpacing: "0.06em" }}>
            <th style={TH}>Track</th>
            <th style={TH}>Class</th>
            <th style={TH}>First seen</th>
            <th style={TH}>Last seen</th>
            <th style={{ ...TH, textAlign: "right" }}>Dwell</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.track_id} style={{ borderBottom: "1px solid var(--border-base)" }}>
              <td style={TD}>{r.track_id}</td>
              <td style={{ ...TD, color: "var(--accent-primary)" }}>{r.class_name}</td>
              <td style={{ ...TD, color: "var(--text-dim)" }}>{fmt(r.first_seen)}</td>
              <td style={{ ...TD, color: "var(--text-dim)" }}>{fmt(r.last_seen)}</td>
              <td style={{ ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--accent-ok)" }}>
                {fmtSecs(r.total_seconds)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const TH: React.CSSProperties = { padding: "6px 10px", textAlign: "left", fontWeight: 600 };
const TD: React.CSSProperties = { padding: "7px 10px" };

// ── ZonePanel ─────────────────────────────────────────────────────────────────

function ZonePanel({ events }: { events: AnalyticEventRaw[] }) {
  if (events.length === 0) {
    return <p style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", margin: "24px 0" }}>No events in this zone.</p>;
  }
  const maxConf  = Math.max(...events.map((e) => e.confidence ?? 0), 0.001);
  const byClass  = events.reduce<Record<string, number>>((acc, e) => {
    acc[e.type] = (acc[e.type] ?? 0) + 1;
    return acc;
  }, {});
  const total = events.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
      {/* Frequency breakdown */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-3)" }}>
        {Object.entries(byClass).map(([cls, cnt]) => (
          <div key={cls} style={{
            padding: "3px 10px",
            borderRadius: "var(--r-pill)",
            background: "var(--primary-dim)",
            color: "var(--accent-primary)",
            fontSize: 12,
            fontWeight: 600,
          }}>
            {cls} · {cnt} ({Math.round((cnt / total) * 100)}%)
          </div>
        ))}
      </div>

      {/* Event list */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)", maxHeight: 220, overflowY: "auto" }}>
        {events.map((ev) => {
          const relFreq = (ev.confidence ?? 0) / maxConf;
          return (
            <div key={ev.event_id} style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-4)",
              padding: "var(--sp-3) var(--sp-4)",
              background: "var(--bg-surface)",
              borderRadius: "var(--r-md)",
              border: "1px solid var(--border-base)",
            }}>
              <span style={{ color: "var(--accent-primary)", fontWeight: 600, fontSize: 13, minWidth: 64 }}>{ev.type}</span>
              <span style={{ color: "var(--text-dim)", fontSize: 12 }}>{new Date(ev.start).toLocaleTimeString()}</span>
              <span style={{ color: "var(--text-dim)", fontSize: 12 }}>{fmtSecs(ev.duration_seconds)}</span>
              <div style={{ flex: 1 }}>
                <div style={{
                  height: 4,
                  borderRadius: 2,
                  background: "var(--border-base)",
                  position: "relative",
                  overflow: "hidden",
                }}>
                  <div style={{
                    position: "absolute", inset: "0 auto 0 0",
                    width: `${Math.round(relFreq * 100)}%`,
                    background: "var(--accent-monitor)",
                    borderRadius: 2,
                  }} />
                </div>
              </div>
              {ev.confidence != null && (
                <span style={{ color: "var(--text-dim)", fontSize: 11, minWidth: 32, textAlign: "right" }}>
                  {Math.round(ev.confidence * 100)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
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

      {/* ── Filters ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-4)",
        flexWrap: "wrap",
      }}>
        {/* Time range */}
        <div style={{ display: "flex", gap: "var(--sp-2)" }}>
          {(Object.keys(RANGE_LABELS) as Range[]).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
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
          onChange={(e) => setMonitorIdx(e.target.value === "" ? null : Number(e.target.value))}
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
            onClick={refresh}
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
