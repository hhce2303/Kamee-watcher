import { useState, type ReactNode } from "react";
import { useRequests } from "../../hooks/useRequests";
import OutputPanel from "../delivery/OutputPanel";
import type { ClipRequest, OperatorInfo } from "../../types/dto";

const STATUS_COLOR: Record<string, string> = {
  pending: "#FBBF24",
  processing: "var(--accent-primary)",
  done: "var(--accent-ok)",
  declined: "var(--accent-record)",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "PENDIENTE",
  processing: "PROCESANDO",
  done: "LISTO",
  declined: "DECLINADA",
};

function fmtDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * Full-screen Supervisor view — port of qml/SupervisorView.qml. Replaces the
 * standard ClipBrowser in the Clips tab for this role: operator names are
 * shown but not navigable (security contract — no path travels to the UI).
 *
 * Unlike QML (which used a hardcoded 47-operator roster as a placeholder),
 * this uses the real `list_all_operators` command — the backend already
 * queries live NAS storages, so there's no reason to fake the data.
 */
export default function SupervisorView() {
  const { operators, myRequests, sending, send } = useRequests();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<OperatorInfo | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [description, setDescription] = useState("");
  const [feedback, setFeedback] = useState<"ok" | "error" | null>(null);

  const filtered = operators.filter((op) => op.name.toLowerCase().includes(search.toLowerCase()));

  function selectOperator(op: OperatorInfo) {
    setSelected(op);
  }

  function setStartToNow() {
    const now = new Date();
    setStart(fmtDate(now));
    if (!end) setEnd(fmtDate(new Date(now.getTime() + 30 * 60000)));
  }

  function addMinutesToEnd(mins: number) {
    if (!start) return;
    const m = start.match(/(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/);
    if (!m) return;
    const base = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
    setEnd(fmtDate(new Date(base.getTime() + mins * 60000)));
  }

  async function handleSend() {
    if (!selected || !start || !end) return;
    const ok = await send({ operator: selected.name, storage: selected.storage, startTime: start, endTime: end, description });
    setFeedback(ok ? "ok" : "error");
    if (ok) {
      setTimeout(() => setFeedback(null), 2500);
      setStart("");
      setEnd("");
      setDescription("");
    }
  }

  return (
    <div style={{ display: "flex", gap: "var(--sp-6)", height: "100%" }}>
      <div style={{ width: "45%", display: "flex", flexDirection: "column", background: "var(--bg-surface)", border: "1px solid var(--border-base)", borderRadius: "var(--r-md)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, height: 44, padding: "0 16px", borderBottom: "1px solid var(--border-base)" }}>
          <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "1.4px" }}>OPERADORES</span>
          <span style={{ padding: "1px 6px", borderRadius: 8, background: "var(--primary-dim)", color: "var(--accent-primary)", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700 }}>
            {operators.length}
          </span>
        </div>
        <div style={{ padding: 8, borderBottom: "1px solid var(--border-base)" }}>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar operador…"
            style={{ width: "100%", height: 32, padding: "0 10px", borderRadius: "var(--r-xs)", border: "1px solid var(--border-base)", background: "var(--bg-base)", color: "var(--text-primary)" }}
          />
        </div>
        <div style={{ flex: 1, overflow: "auto", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, padding: 10, alignContent: "start" }}>
          {filtered.map((op) => (
            <OperatorCard key={op.name} operator={op} selected={selected?.name === op.name} onClick={() => selectOperator(op)} />
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 32 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <h2 style={{ fontSize: 22, fontWeight: 600 }}>Solicitar clip</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
              Selecciona un operador en el panel izquierdo y define el rango de tiempo del incidente.
            </p>
          </div>

          <FormRow label="Operador" helper="Haz click en un operador del panel izquierdo.">
            <input value={selected?.name ?? ""} readOnly placeholder="Operator-28" style={fieldStyle(240)} />
          </FormRow>

          <FormRow label="Inicio del incidente" helper="Fecha y hora local, formato: YYYY-MM-DD HH:MM">
            <div style={{ display: "flex", gap: 8 }}>
              <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="2026-06-04 14:00" style={fieldStyle(200)} />
              <button type="button" onClick={setStartToNow} style={miniBtnStyle}>Ahora</button>
            </div>
          </FormRow>

          <FormRow label="Fin del incidente" helper="Incluir margen post-incidente (ej. +30 min)">
            <div style={{ display: "flex", gap: 8 }}>
              <input value={end} onChange={(e) => setEnd(e.target.value)} placeholder="2026-06-04 14:30" style={fieldStyle(200)} />
              <button type="button" onClick={() => addMinutesToEnd(15)} style={miniBtnStyle}>+15m</button>
              <button type="button" onClick={() => addMinutesToEnd(30)} style={miniBtnStyle}>+30m</button>
              <button type="button" onClick={() => addMinutesToEnd(60)} style={miniBtnStyle}>+1h</button>
            </div>
          </FormRow>

          <FormRow label="Descripción del incidente" helper="Contexto para IT: tipo de incidente, hora exacta, observaciones.">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Incidente reportado a las 14:15 — revisar operador…"
              rows={3}
              style={{ ...fieldStyle(0), width: "100%", resize: "vertical" }}
            />
          </FormRow>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              type="button"
              disabled={!selected || !start || !end || sending}
              onClick={handleSend}
              style={{ width: 160, height: 38, borderRadius: "var(--r-sm)", border: "none", background: selected && start && end ? "var(--accent-primary)" : "rgba(255,255,255,0.07)", color: selected && start && end ? "var(--bg-base)" : "var(--text-dim)", fontSize: 15, fontWeight: 600, cursor: "pointer" }}
            >
              {sending ? "Enviando…" : "Enviar a IT"}
            </button>
            {feedback && (
              <span style={{ color: feedback === "ok" ? "var(--accent-ok)" : "var(--accent-record)", fontSize: 14 }}>
                {feedback === "ok" ? "✓ Solicitud enviada" : "✗ Error al enviar"}
              </span>
            )}
          </div>
        </div>

        <RequestOutbox requests={myRequests} />

        <OutputPanel />
      </div>
    </div>
  );
}

function OperatorCard({ operator, selected, onClick }: { operator: OperatorInfo; selected: boolean; onClick: () => void }) {
  const initials = operator.name.match(/[-_ ](\w+)$/)?.[1] ?? operator.name.slice(0, 2).toUpperCase();
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        aspectRatio: "1",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 7,
        borderRadius: "var(--r-md)",
        background: selected ? "var(--primary-dim)" : "var(--bg-surface)",
        border: `${selected ? 1.5 : 1}px solid ${selected ? "var(--accent-primary)" : "var(--border-base)"}`,
        cursor: "pointer",
        position: "relative",
      }}
    >
      {selected && <span style={{ position: "absolute", top: 6, right: 6, width: 16, height: 16, borderRadius: 8, background: "var(--accent-primary)", color: "var(--bg-base)", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" }}>✓</span>}
      <span style={{ width: 38, height: 38, borderRadius: "var(--r-sm)", background: selected ? "rgba(56,189,248,0.22)" : "rgba(129,140,248,0.10)", display: "flex", alignItems: "center", justifyContent: "center", color: selected ? "var(--accent-primary)" : "var(--accent-monitor)", fontFamily: "var(--font-mono)", fontWeight: 700 }}>
        {initials}
      </span>
      <span style={{ color: selected ? "var(--text-primary)" : "var(--text-muted)", fontSize: 12, fontWeight: selected ? 600 : 400 }}>{operator.name}</span>
      <span style={{ padding: "0 4px", borderRadius: 3, border: "1px solid var(--border-subtle)", color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 10 }}>{operator.storage}</span>
    </button>
  );
}

function RequestOutbox({ requests }: { requests: ClipRequest[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid var(--border-base)", paddingBottom: 8 }}>
        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "1.4px" }}>MIS SOLICITUDES</span>
        {requests.length > 0 && (
          <span style={{ padding: "1px 6px", borderRadius: 9, background: "var(--primary-dim)", color: "var(--accent-primary)", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700 }}>
            {requests.length}
          </span>
        )}
      </div>
      {requests.length === 0 && <p style={{ color: "var(--text-dim)", fontSize: 14 }}>No hay solicitudes enviadas todavía.</p>}
      {requests.map((r) => (
        <div key={r.id} style={{ borderRadius: "var(--r-sm)", background: "var(--bg-surface)", border: "1px solid var(--border-base)", padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ padding: "1px 6px", borderRadius: 4, background: "rgba(0,0,0,0.25)", color: STATUS_COLOR[r.status], fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700 }}>
              {STATUS_LABEL[r.status] ?? r.status.toUpperCase()}
            </span>
            <span style={{ flex: 1, color: "var(--text-primary)", fontSize: 15, fontWeight: 600 }}>{r.operator} — {r.storage}</span>
            <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{r.created_at.slice(0, 16).replace("T", " ")}</span>
          </div>
          <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 13 }}>{r.start_time} → {r.end_time}</span>
          {r.description && <p style={{ color: "var(--text-dim)", fontSize: 13 }}>{r.description}</p>}
        </div>
      ))}
    </div>
  );
}

function FormRow({ label, helper, children }: { label: string; helper: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ color: "var(--text-primary)", fontSize: 13, fontWeight: 600 }}>{label}</label>
      <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{helper}</span>
      {children}
    </div>
  );
}

function fieldStyle(width: number) {
  return {
    width: width || undefined,
    height: 32,
    padding: "0 10px",
    borderRadius: "var(--r-sm)",
    border: "1px solid var(--border-base)",
    background: "var(--bg-base)",
    color: "var(--text-primary)",
    fontFamily: "var(--font-mono)",
    fontSize: 14,
  } as const;
}

const miniBtnStyle = {
  height: 32,
  padding: "0 12px",
  borderRadius: "var(--r-sm)",
  border: "1px solid var(--border-base)",
  background: "var(--bg-surface)",
  color: "var(--text-primary)",
  fontSize: 13,
  cursor: "pointer",
} as const;
