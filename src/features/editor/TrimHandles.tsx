import { useState, useEffect } from "react";

interface TrimHandlesProps {
  sourceDurationS: number;
  inPointS: number;
  outPointS: number;
  onCommit: (inPointS: number, outPointS: number) => void;
}

/**
 * Numeric in/out trim editor for the selected reel clip.
 *
 * TD-7: there is no frame-exact scrub from `<video>.currentTime` — these are
 * wall-clock seconds within the source file, good enough for marking a
 * rough range; the export itself re-cuts server-side (FFmpegEditorExportAdapter).
 */
export default function TrimHandles({ sourceDurationS, inPointS, outPointS, onCommit }: TrimHandlesProps) {
  const [inText, setInText] = useState(inPointS.toFixed(1));
  const [outText, setOutText] = useState(outPointS.toFixed(1));

  useEffect(() => {
    setInText(inPointS.toFixed(1));
    setOutText(outPointS.toFixed(1));
  }, [inPointS, outPointS]);

  function commit() {
    const inS = Math.max(0, Math.min(Number(inText) || 0, sourceDurationS));
    const outS = Math.max(inS, Math.min(Number(outText) || sourceDurationS, sourceDurationS));
    onCommit(inS, outS);
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <label style={{ color: "var(--text-muted)", fontSize: 12 }}>
        In
        <input value={inText} onChange={(e) => setInText(e.target.value)} onBlur={commit} style={inputStyle} />
      </label>
      <label style={{ color: "var(--text-muted)", fontSize: 12 }}>
        Out
        <input value={outText} onChange={(e) => setOutText(e.target.value)} onBlur={commit} style={inputStyle} />
      </label>
      <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 12 }}>/ {sourceDurationS.toFixed(1)}s</span>
    </div>
  );
}

const inputStyle = {
  width: 64,
  marginLeft: 6,
  height: 28,
  padding: "0 8px",
  borderRadius: "var(--r-sm)",
  border: "1px solid var(--border-base)",
  background: "var(--bg-base)",
  color: "var(--text-primary)",
  fontFamily: "var(--font-mono)",
  fontSize: 12,
} as const;
