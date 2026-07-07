import { useAppStore } from "../stores/appStore";

function fmtTime(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/**
 * Collapsed by default — a badge grows on an anchored tab, nothing appears unsolicited.
 * Expanding shows the full bounded log history (see appStore's MAX_LOG_HISTORY), not a
 * toast that vanishes before you finish reading it.
 */
export default function LogDrawer() {
  const logs = useAppStore((s) => s.logs);
  const unreadCount = useAppStore((s) => s.unreadCount);
  const drawerOpen = useAppStore((s) => s.drawerOpen);
  const toggle = useAppStore((s) => s.toggleLogDrawer);

  return (
    <div className="log-drawer">
      {drawerOpen && (
        <div className="log-drawer__panel">
          {logs.length === 0 ? (
            <div className="log-drawer__empty">Sin actividad todavía.</div>
          ) : (
            logs.map((entry) => (
              <div key={entry.id} className={`log-drawer__row${entry.level === "error" ? " log-drawer__row--error" : ""}`}>
                <span className="log-drawer__msg">{entry.message}</span>
                <span className="log-drawer__ts">{fmtTime(entry.ts)}</span>
              </div>
            ))
          )}
        </div>
      )}
      <button type="button" className="log-drawer__tab" onClick={toggle} aria-expanded={drawerOpen}>
        <span>{drawerOpen ? "▾" : "▴"} Historial</span>
        {unreadCount > 0 && <span className="log-drawer__badge">{unreadCount > 99 ? "99+" : unreadCount}</span>}
      </button>
    </div>
  );
}
