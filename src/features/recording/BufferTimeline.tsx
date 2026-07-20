export interface EventMarker {
  sec: number;
  tag: string;
}

interface BufferTimelineProps {
  recordSec: number;
  eventMarkers: EventMarker[];
  windowSec?: number;
  segCount?: number;
}

/** Rolling buffer visualization — port of qml/BufferTimeline.qml. */
export default function BufferTimeline({
  recordSec,
  eventMarkers,
  windowSec = 120,
  segCount = 60,
}: BufferTimelineProps) {
  const filledSec = Math.min(recordSec, windowSec);
  const segsFilled = Math.floor((filledSec / windowSec) * segCount);
  const bufferMB = filledSec * 0.85;
  const windowMin = Math.floor(windowSec / 60);

  return (
    <div
      style={{
        background: "var(--bg-surface)",
        borderRadius: "var(--r-md)",
        border: "1px solid var(--border-base)",
        padding: 14,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ color: "var(--text-muted)", fontSize: 11, fontWeight: 600, letterSpacing: "1.4px" }}>
          ROLLING BUFFER
        </span>
        <span
          style={{
            padding: "2px 6px",
            borderRadius: 3,
            background: "var(--primary-dim)",
            color: "var(--accent-primary)",
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            fontWeight: 600,
          }}
        >
          {windowMin} MIN
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
          {Math.floor(filledSec / 60)}:{String(filledSec % 60).padStart(2, "0")} / {windowMin}:00
        </span>
        <div style={{ width: 1, height: 10, background: "var(--border-base)" }} />
        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
          {Math.min(segsFilled, segCount)}/{segCount} seg
        </span>
        <div style={{ width: 1, height: 10, background: "var(--border-base)" }} />
        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
          ~{bufferMB.toFixed(0)} MB
        </span>
      </div>

      <div style={{ position: "relative", height: 28 }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            background: "var(--bg-base)",
            borderRadius: 3,
            border: "1px solid var(--border-base)",
            overflow: "hidden",
          }}
        >
          {Array.from({ length: segCount }, (_, i) => (
            <div
              key={i}
              style={{
                flex: 1,
                borderRight: i < segCount - 1 ? "1px solid rgba(30,41,59,0.6)" : "none",
                background: i < segsFilled ? "var(--accent-primary)" : "transparent",
                opacity: i < segsFilled ? (i / segCount) * 0.5 + 0.4 : 0,
                transition: "opacity 240ms ease",
              }}
            />
          ))}
        </div>

        {/* NOW indicator */}
        <div style={{ position: "absolute", right: 0, top: -3, bottom: -3, width: 2, background: "var(--accent-record)" }} />
        <span
          style={{
            position: "absolute",
            right: -4,
            bottom: "100%",
            marginBottom: 2,
            color: "var(--accent-record)",
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            fontWeight: 700,
          }}
        >
          NOW
        </span>

        {/* Event pins */}
        {eventMarkers.map((m, i) => {
          const relAge = recordSec - m.sec;
          if (relAge < 0 || relAge >= windowSec) return null;
          const leftPct = (1 - relAge / windowSec) * 100;
          return (
            <div
              key={i}
              title={m.tag}
              style={{ position: "absolute", left: `${leftPct}%`, top: -10, bottom: -10, width: 1 }}
            >
              <div style={{ width: 6, height: 6, borderRadius: 3, background: "var(--accent-yellow)", marginLeft: -3 }} />
              <div style={{ width: 1, flex: 1, background: "var(--accent-yellow)", opacity: 0.6, marginLeft: 2.5, height: "100%" }} />
            </div>
          );
        })}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
        <span>−{windowMin}:00</span>
        <span>−{Math.floor(windowMin * 0.75)}:30</span>
        <span>−{Math.floor(windowMin / 2)}:00</span>
        <span>−0:30</span>
        <span style={{ color: "var(--accent-record)", fontWeight: 600 }}>NOW</span>
      </div>
    </div>
  );
}
