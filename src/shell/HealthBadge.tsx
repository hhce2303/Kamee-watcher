import { useEffect, useState } from "react";

interface HealthReading {
  cpu: number;
  diskFreeGb: number;
  fps: number;
}

/**
 * CPU/DISK/FPS titlebar readout — port of qml/HealthBadge.qml.
 *
 * QML mocks these values too (no backend telemetry wired to the UI yet); a
 * real `get_health` IPC command is tracked as future work (P3 in the
 * migration plan) rather than invented here.
 */
export default function HealthBadge() {
  const [reading, setReading] = useState<HealthReading>({ cpu: 12, diskFreeGb: 480, fps: 30 });

  useEffect(() => {
    const id = setInterval(() => {
      setReading((r) => ({
        cpu: clamp(r.cpu + (Math.random() - 0.5) * 4, 5, 45),
        diskFreeGb: r.diskFreeGb,
        fps: 30,
      }));
    }, 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: "flex", gap: "var(--sp-4)", fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
      <span>CPU {reading.cpu.toFixed(0)}%</span>
      <span>DISK {reading.diskFreeGb.toFixed(0)}GB</span>
      <span>{reading.fps}FPS</span>
    </div>
  );
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}
