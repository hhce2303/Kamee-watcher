import { useEffect, useRef } from "react";
import type { CountByClass } from "../../types/dto";

const BAR_COLORS = [
  "#38bdf8", "#818cf8", "#34d399", "#facc15",
  "#fb923c", "#f472b6", "#a78bfa", "#4ade80",
];

/** Bar chart of detection counts by class — hand-rolled canvas, no chart lib needed for this shape. */
export default function CountsChart({ counts }: { counts: CountByClass[] }) {
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
