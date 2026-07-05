import { useIpc } from "../hooks/useIpc";

export default function SettingsTab() {
  const { send } = useIpc();

  async function handleSetRole(role: string) {
    try {
      await send("set_role", { role });
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-7)", maxWidth: 480 }}>
      <div>
        <p style={{ color: "var(--text-muted)", fontSize: 11, marginBottom: "var(--sp-4)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Role
        </p>
        <div style={{ display: "flex", gap: "var(--sp-3)" }}>
          {["operator", "it", "supervisor"].map((role) => (
            <button
              key={role}
              onClick={() => handleSetRole(role)}
              style={{
                padding: "6px 16px",
                borderRadius: "var(--r-sm)",
                border: "1px solid var(--border-subtle)",
                background: "var(--bg-surface)",
                color: "var(--text-muted)",
                fontFamily: "var(--font-sans)",
                fontSize: 13,
                cursor: "pointer",
                textTransform: "capitalize",
              }}
            >
              {role}
            </button>
          ))}
        </div>
      </div>

      <div className="placeholder-tab" style={{ alignItems: "flex-start", height: "auto" }}>
        <p>
          Full settings UI (clips dir, codec, autorecord, autostart) will be ported from the
          QML SettingsView in Fase 2b.
        </p>
      </div>
    </div>
  );
}
