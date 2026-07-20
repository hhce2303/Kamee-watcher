import { useEffect, useState } from "react";
import { previewUrl } from "../../lib/mediaUrl";
import type { MonitorDTO } from "../../types/dto";

interface MonitorTileProps {
  monitor: MonitorDTO;
  isRecording: boolean;
  fillContainer?: boolean;
}

const PREVIEW_INTERVAL_MS = 500; // matches FFmpegRecorderAdapter's preview_fps=2

/**
 * Live monitor preview tile. Served by the `watcher://` custom protocol
 * (TD-5: never over JSON invoke) — a plain <img> polling with a cache-busting
 * query param is simplest and avoids the WS/MJPEG plumbing for a 2 fps feed.
 */
export default function MonitorTile({ monitor, isRecording, fillContainer }: MonitorTileProps) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!monitor.selected) return;
    const id = setInterval(() => setTick((t) => t + 1), PREVIEW_INTERVAL_MS);
    return () => clearInterval(id);
  }, [monitor.selected]);

  return (
    <div
      style={{
        position: "relative",
        aspectRatio: fillContainer ? "auto" : "16 / 9",
        width: fillContainer ? "100%" : "auto",
        height: fillContainer ? "100%" : "auto",
        borderRadius: fillContainer ? 0 : "var(--r-md)",
        overflow: "hidden",
        background: "var(--bg-base)",
        border: fillContainer ? "none" : `1px solid ${monitor.selected ? "var(--accent-monitor)" : "var(--border-base)"}`,
      }}
    >
      {monitor.selected ? (
        <img
          src={`${previewUrl(monitor.index)}?t=${tick}`}
          alt={monitor.name}
          style={{ width: "100%", height: "100%", objectFit: fillContainer ? "contain" : "cover", display: "block" }}
        />
      ) : (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-dim)",
            fontSize: 12,
          }}
        >
          Pantalla desactivada
        </div>
      )}

      <div
        style={{
          position: "absolute",
          top: 8,
          left: 8,
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "2px 8px",
          borderRadius: "var(--r-xs)",
          background: "rgba(7, 9, 15, 0.72)",
          fontSize: 11,
          color: "var(--text-primary)",
          fontFamily: "var(--font-mono)",
        }}
      >
        {isRecording && monitor.selected && (
          <span style={{ width: 6, height: 6, borderRadius: 3, background: "var(--accent-record)" }} />
        )}
        {monitor.name}
      </div>
    </div>
  );
}
