import { useState } from "react";
import { setRole } from "../../lib/ipc";

const ROLES = [
  {
    id: "operator",
    icon: "📡",
    title: "Operador",
    sub: "Monitoreo 24/7",
    desc: "Graba continuamente todas las pantallas asignadas. La ventana permanece siempre activa y la grabación nunca se interrumpe. Sin acceso a ajustes ni clips.",
  },
  {
    id: "supervisor",
    icon: "🔍",
    title: "Supervisor",
    sub: "Auditoría y revisión",
    desc: "Accede al reproductor de clips desde la red o unidad local. No graba. Ideal para estaciones de supervisión o revisión de incidentes.",
  },
  {
    id: "it",
    icon: "⚙️",
    title: "IT",
    sub: "Administración completa",
    desc: "Ajustes completos: encoder, almacenamiento, editor de clips y cambio de rol con PIN. Para el personal técnico responsable del despliegue.",
  },
] as const;

/**
 * First-run role picker — port of qml/RoleSetupWizard.qml. Shown by App.tsx
 * while `settings.role === ""`. Backend persists the role and publishes
 * `role_changed`; appStore's subscription refreshes policy automatically, so
 * no relaunch/reload is needed on the React side (unlike the QML process
 * relaunch this replaces).
 */
export default function RoleSetupWizard() {
  const [selected, setSelected] = useState<string>("");
  const [configuring, setConfiguring] = useState(false);

  async function confirm() {
    if (!selected || configuring) return;
    setConfiguring(true);
    try {
      await setRole(selected);
    } finally {
      setConfiguring(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100vh", padding: 40 }}>
      <div style={{ width: "min(100%, 860px)" }}>
        <div style={{ textAlign: "center", marginBottom: 48 }}>
          <div style={{ color: "var(--accent-primary)", fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, letterSpacing: "2px" }}>
            THE WATCHER
          </div>
          <h1 style={{ fontSize: 30, fontWeight: 600, margin: "10px 0" }}>Configura este equipo</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 15, lineHeight: 1.5 }}>
            Selecciona el rol de este PC. Esta configuración se guarda localmente y
            <br />
            puede cambiarse después con el PIN IT.
          </p>
        </div>

        <div style={{ display: "flex", gap: 16 }}>
          {ROLES.map((role) => {
            const isSelected = selected === role.id;
            return (
              <button
                key={role.id}
                type="button"
                onClick={() => setSelected(role.id)}
                style={{
                  flex: 1,
                  height: 230,
                  padding: 24,
                  textAlign: "left",
                  borderRadius: "var(--r-md)",
                  background: isSelected ? "var(--primary-dim)" : "var(--bg-surface)",
                  border: `${isSelected ? 2 : 1}px solid ${isSelected ? "var(--accent-primary)" : "var(--border-base)"}`,
                  cursor: "pointer",
                  position: "relative",
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                {isSelected && (
                  <span style={{ position: "absolute", top: 14, right: 14, width: 10, height: 10, borderRadius: 5, background: "var(--accent-primary)" }} />
                )}
                <span style={{ fontSize: 30 }}>{role.icon}</span>
                <div>
                  <div style={{ color: "var(--text-primary)", fontSize: 18, fontWeight: 600 }}>{role.title}</div>
                  <div style={{ color: "var(--accent-primary)", fontFamily: "var(--font-mono)", fontSize: 12, letterSpacing: "0.8px" }}>{role.sub}</div>
                </div>
                <p style={{ color: "var(--text-muted)", fontSize: 14, lineHeight: 1.5 }}>{role.desc}</p>
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", justifyContent: "center", marginTop: 32 }}>
          <button
            type="button"
            disabled={!selected || configuring}
            onClick={confirm}
            style={{
              width: 240,
              height: 44,
              borderRadius: "var(--r-sm)",
              border: "none",
              background: selected ? "var(--accent-primary)" : "rgba(255,255,255,0.08)",
              color: selected ? "var(--bg-base)" : "var(--text-dim)",
              fontSize: 15,
              fontWeight: 600,
              cursor: selected ? "pointer" : "not-allowed",
            }}
          >
            {configuring ? "Configurando…" : "Configurar este equipo"}
          </button>
        </div>
      </div>
    </div>
  );
}
