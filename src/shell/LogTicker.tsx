import { useAppStore } from "../stores/appStore";

/**
 * Ambient "something just happened" slot inside the existing Statusbar — never a new
 * on-screen element, never shifts layout. An unresolved error pins itself here (red) until
 * the user opens the LogDrawer; otherwise it shows the most recent log line.
 */
export default function LogTicker() {
  const logs = useAppStore((s) => s.logs);
  const lastError = useAppStore((s) => s.lastError);
  const entry = lastError ?? logs[0];

  if (!entry) return null;

  return (
    <span
      key={entry.id}
      className="log-ticker"
      style={{ color: entry.level === "error" ? "var(--accent-record)" : "var(--text-muted)" }}
      title={entry.message}
    >
      {entry.message}
    </span>
  );
}
