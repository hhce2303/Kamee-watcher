import { useAppStore } from "../stores/appStore";

/** Live notification strip — driven by log_message / *_failed bus events. */
export default function NotificationStrip() {
  const notifications = useAppStore((s) => s.notifications);
  const dismiss = useAppStore((s) => s.dismissNotification);

  if (notifications.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "var(--sp-3) var(--sp-5)" }}>
      {notifications.map((n) => (
        <div
          key={n.id}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-4)",
            padding: "var(--sp-3) var(--sp-4)",
            borderRadius: "var(--r-sm)",
            background: n.level === "error" ? "var(--record-dim)" : "var(--primary-dim)",
            color: n.level === "error" ? "var(--accent-record)" : "var(--accent-primary)",
            fontSize: 12,
          }}
        >
          <span style={{ flex: 1 }}>{n.message}</span>
          <button
            type="button"
            onClick={() => dismiss(n.id)}
            style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", fontSize: 14 }}
            aria-label="Descartar"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
