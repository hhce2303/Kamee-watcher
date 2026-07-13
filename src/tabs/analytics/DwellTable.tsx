import type { CSSProperties } from "react";
import type { DwellRecord } from "../../types/dto";
import { fmtSecs, fmtTime } from "./format";

const TH: CSSProperties = { padding: "6px 10px", textAlign: "left", fontWeight: 600 };
const TD: CSSProperties = { padding: "7px 10px" };

/** Per-tracked-object dwell-time table, longest dwell first. */
export default function DwellTable({ rows }: { rows: DwellRecord[] }) {
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
              <td style={{ ...TD, color: "var(--text-dim)" }}>{fmtTime(r.first_seen)}</td>
              <td style={{ ...TD, color: "var(--text-dim)" }}>{fmtTime(r.last_seen)}</td>
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
