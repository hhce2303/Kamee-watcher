import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import WSettingsRow from "../../components/WSettingsRow";
import WToggle from "../../components/WToggle";
import WDropdown from "../../components/WDropdown";
import WSeg from "../../components/WSeg";
import WPathInput from "../../components/WPathInput";
import WHotkey from "../../components/WHotkey";
import { useSettingsForm, DRIVERS } from "../../hooks/useSettingsForm";
import { policyFor } from "../../lib/policy";

const DRIVER_OPTIONS = DRIVERS.map((d) => ({ value: d, label: d }));
const HOTKEYS = [
  { label: "Marcar evento", keys: ["Space"] },
  { label: "Cancelar acción", keys: ["Esc"] },
  { label: "Ir a Grabación", keys: ["Ctrl", "1"] },
  { label: "Ir a Clips", keys: ["Ctrl", "2"] },
  { label: "Mini-modo", keys: ["Ctrl", "3"] },
  { label: "Ajustes", keys: ["Ctrl", "4"] },
];

/**
 * Full settings view — port of qml/SettingsView.qml, scoped to rows backed by
 * a real IPC command. QML also has capture/audio/event-timing rows that are
 * .env-only config with no facade method (no `Set*` command exists for them)
 * — inventing new backend surface for those is out of scope here; they stay
 * on `.env`/config.py until a real use case needs runtime control.
 */
export default function SettingsView() {
  const { settings, restartState, restartError, actions } = useSettingsForm();
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);

  if (!settings) return null;

  const policy = policyFor(settings.role);
  const canChangeRole = policy.canChangeRole || settings.it_unlocked;

  async function handleUnlock() {
    const ok = await actions.unlockIt(pin);
    setPinError(ok ? null : "PIN incorrecto");
    if (ok) setPin("");
  }

  return (
    <div style={{ maxWidth: 640, display: "flex", flexDirection: "column" }}>
      <WSettingsRow label="Directorio de clips" helper="Carpeta donde se guardan los clips finales." vertical>
        <WPathInput
          path={settings.clips_dir}
          onPathChange={actions.setClipsDir}
          onBrowse={async () => {
            const dir = await open({ directory: true, defaultPath: settings.clips_dir });
            if (typeof dir === "string") await actions.setClipsDir(dir);
          }}
        />
      </WSettingsRow>

      <WSettingsRow label="Driver / aceleración" helper="Encoder de hardware preferido para la grabación.">
        <WDropdown options={DRIVER_OPTIONS} value={settings.driver} onChange={actions.setDriver} />
      </WSettingsRow>

      <WSettingsRow label="Códec" helper="H.264 es universalmente compatible; HEVC ahorra ~40-50% de espacio.">
        <WSeg
          options={[
            { value: "h264", label: "H.264" },
            { value: "hevc", label: "H.265 / HEVC" },
          ]}
          value={settings.codec}
          onSelect={actions.setCodec}
        />
      </WSettingsRow>

      <WSettingsRow label="Aplicar cambios ahora" helper="Reinicia la grabación en vivo con el driver/códec actuales.">
        <button
          type="button"
          disabled={restartState === "restarting"}
          onClick={actions.applyEncoderNow}
          style={applyBtnStyle(restartState)}
        >
          {restartState === "restarting" ? "Aplicando…" : restartState === "done" ? "Aplicado ✓" : restartState === "error" ? "Error" : "Aplicar ahora"}
        </button>
      </WSettingsRow>
      {restartState === "error" && restartError && (
        <p style={{ color: "var(--accent-record)", fontSize: 12, marginTop: -8 }}>{restartError}</p>
      )}

      <WSettingsRow label="Iniciar con Windows" helper="Registra el arranque automático al iniciar sesión.">
        <WToggle checked={settings.autostart} onToggle={actions.setAutostart} />
      </WSettingsRow>

      <WSettingsRow label="Iniciar grabación al abrir" helper="Arranca el buffer continuo automáticamente.">
        <WToggle checked={settings.autorecord} onToggle={actions.setAutorecord} />
      </WSettingsRow>

      <WSettingsRow label="Atajos" vertical>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {HOTKEYS.map((h) => (
            <div key={h.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{h.label}</span>
              <WHotkey keys={h.keys} />
            </div>
          ))}
        </div>
      </WSettingsRow>

      <WSettingsRow label="Rol de este equipo" helper={canChangeRole ? undefined : "Ingresa el PIN de IT para cambiar el rol."}>
        {canChangeRole ? (
          <WSeg
            options={[
              { value: "operator", label: "Operador" },
              { value: "supervisor", label: "Supervisor" },
              { value: "it", label: "IT" },
            ]}
            value={settings.role}
            onSelect={actions.setRole}
          />
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="PIN IT"
              style={{ width: 100, height: 32, padding: "0 10px", borderRadius: "var(--r-sm)", border: "1px solid var(--border-base)", background: "var(--bg-base)", color: "var(--text-primary)" }}
            />
            <button type="button" onClick={handleUnlock} style={applyBtnStyle("idle")}>
              Desbloquear
            </button>
          </div>
        )}
      </WSettingsRow>
      {pinError && <p style={{ color: "var(--accent-record)", fontSize: 12, marginTop: -8 }}>{pinError}</p>}

      {settings.role === "it" && <ItWsPortNotice />}
    </div>
  );
}

/** IT WS port management (open_it_ws_port + host list) has no backend command
 * beyond the unrouted `OpenItWsPort` DTO — descoped per the migration plan
 * (P3), shown here only as a static notice so IT knows it's pending. */
function ItWsPortNotice() {
  return (
    <WSettingsRow label="Servidor WS (IT)" helper="Gestión del puerto de requests Supervisor↔IT pendiente de exponer por IPC.">
      <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 12 }}>No disponible aún</span>
    </WSettingsRow>
  );
}

function applyBtnStyle(state: string) {
  return {
    height: 32,
    padding: "0 16px",
    borderRadius: "var(--r-sm)",
    border: "none",
    background: state === "done" ? "var(--accent-ok)" : state === "error" ? "var(--accent-record)" : "var(--accent-primary)",
    color: "var(--bg-base)",
    fontSize: 13,
    fontWeight: 700,
    cursor: state === "restarting" ? "not-allowed" : "pointer",
  } as const;
}
