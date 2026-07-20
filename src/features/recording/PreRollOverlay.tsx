import { useEffect, useState } from "react";
import Modal from "../../components/Modal";

interface PreRollOverlayProps {
  initialCount?: number;
  onFinished: () => void;
  onCancelled: () => void;
}

/** Countdown modal shown right after MARCAR EVENTO — port of qml/PreRollOverlay.qml. */
export default function PreRollOverlay({ initialCount = 3, onFinished, onCancelled }: PreRollOverlayProps) {
  const [count, setCount] = useState(initialCount);

  useEffect(() => {
    if (count <= 0) {
      onFinished();
      return;
    }
    const id = setTimeout(() => setCount((c) => c - 1), 1000);
    return () => clearTimeout(id);
  }, [count, onFinished]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancelled();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancelled]);

  const progress = count / initialCount;
  const circumference = 2 * Math.PI * 68;

  return (
    <Modal onClose={onCancelled}>
      <div style={{ width: 260, display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
        <span
          style={{
            padding: "4px 11px",
            borderRadius: "var(--r-xs)",
            background: "var(--primary-dim)",
            border: "1px solid var(--accent-primary)",
            color: "var(--accent-primary)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: "1.2px",
          }}
        >
          📍 CAPTURANDO EVENTO
        </span>

        <svg width={140} height={140} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={70} cy={70} r={68} fill="none" stroke="var(--border-base)" strokeWidth={2} />
          <circle
            cx={70}
            cy={70}
            r={68}
            fill="none"
            stroke="var(--accent-primary)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - progress)}
            style={{ transition: "stroke-dashoffset 950ms linear" }}
          />
          <text
            x={70}
            y={70}
            transform="rotate(90 70 70)"
            textAnchor="middle"
            dominantBaseline="central"
            fill="var(--accent-primary)"
            fontFamily="var(--font-mono)"
            fontSize={56}
            fontWeight={700}
          >
            {count}
          </text>
        </svg>

        <div style={{ textAlign: "center" }}>
          <div style={{ color: "var(--text-primary)", fontSize: 16, fontWeight: 600 }}>Marcando evento</div>
          <div style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "1px" }}>
            2 MIN PRE · 2 MIN POST · CLIP DE 4 MIN
          </div>
        </div>

        <button
          type="button"
          onClick={onCancelled}
          style={{
            height: 30,
            padding: "0 14px",
            borderRadius: "var(--r-sm)",
            background: "transparent",
            border: "1px solid var(--border-base)",
            color: "var(--text-muted)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: "1px",
            cursor: "pointer",
          }}
        >
          CANCELAR · ESC
        </button>
      </div>
    </Modal>
  );
}
