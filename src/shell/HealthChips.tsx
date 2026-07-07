import { useAppStore } from "../stores/appStore";
import { useMediaRoots } from "../hooks/useMediaRoots";
import { useOutputPanel } from "../hooks/useOutputPanel";

type Tone = "ok" | "warn" | "error";

const TONE_COLOR: Record<Tone, string> = {
  ok: "var(--accent-ok)",
  warn: "#FBBF24",
  error: "var(--accent-record)",
};

export function StatusChip({ label, tone }: { label: string; tone: Tone }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)" }}>
      <span style={{ width: 6, height: 6, borderRadius: 3, background: TONE_COLOR[tone] }} />
      {label}
    </span>
  );
}

/**
 * WS/NAS/OD connectivity chips + role badge for the IT header — port of the
 * QML header's WS/NAS/OD health chips + role badge. Distinct from
 * HealthBadge.tsx (CPU/DISK/FPS, mocked, used by AppShell) — a different
 * concern with real signals already available client-side.
 */
export function ITHealthChips() {
  const ipcConnected = useAppStore((s) => s.ipcConnected);
  const role = useAppStore((s) => s.settings?.role);
  const { roots, error: nasError } = useMediaRoots();
  const { state: odState } = useOutputPanel();

  const nasTone: Tone = nasError ? "error" : roots ? "ok" : "warn";
  const odTone: Tone = odState === "error" ? "error" : odState === "linked" || odState === "working" ? "ok" : "warn";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <StatusChip label="WS" tone={ipcConnected ? "ok" : "error"} />
      <StatusChip label="NAS" tone={nasTone} />
      <StatusChip label="OD" tone={odTone} />
      {role && (
        <span style={{ padding: "1px 6px", borderRadius: 4, border: "1px solid var(--border-subtle)", color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.6px" }}>
          {role.toUpperCase()}
        </span>
      )}
    </div>
  );
}
