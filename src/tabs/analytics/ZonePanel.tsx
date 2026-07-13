import type { AnalyticEventRaw } from "../../hooks/useLiveAnalytics";
import { fmtSecs } from "./format";

/** Frequency breakdown + event list for a named zone query. */
export default function ZonePanel({ events }: { events: AnalyticEventRaw[] }) {
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
