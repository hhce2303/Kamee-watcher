import { useInboxRequests } from "../../hooks/useInboxRequests";
import type { ClipRequest } from "../../types/dto";

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

const GROUPS: { key: ClipRequest["status"]; label: string }[] = [
  { key: "pending", label: "PENDIENTES" },
  { key: "processing", label: "PROCESANDO" },
  { key: "done", label: "LISTAS" },
  { key: "declined", label: "DECLINADAS" },
];

interface ITInboxPanelProps {
  /** Opens a request in the editor (ITEditorView's "cola" view); omitted when
   * embedded read-only in RecordingView's Ctrl+I panel. */
  onOpen?: (request: ClipRequest) => void;
}

/** IT inbox of clip requests from Supervisors — port of qml/ITInboxPanel.qml. */
export default function ITInboxPanel({ onOpen }: ITInboxPanelProps) {
  const { requests, setStatus } = useInboxRequests();
  const pendingCount = requests.filter((r) => r.status === "pending").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", border: "1px solid var(--border-base)", borderRadius: "var(--r-md)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, height: 44, padding: "0 16px", background: "var(--bg-elevated)", borderBottom: "1px solid var(--border-base)" }}>
        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "1.4px" }}>BANDEJA IT</span>
        {pendingCount > 0 && (
          <span style={{ padding: "1px 6px", borderRadius: 9, background: "rgba(251,191,36,0.2)", color: "#FBBF24", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700 }}>
            {pendingCount}
          </span>
        )}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 16 }}>
        {requests.length === 0 && (
          <p style={{ color: "var(--text-dim)", fontSize: 13, textAlign: "center", marginTop: 20 }}>Sin solicitudes.</p>
        )}
        {GROUPS.map((g) => {
          const group = requests.filter((r) => r.status === g.key);
          if (group.length === 0) return null;
          return (
            <div key={g.key} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "1px" }}>
                {g.label} ({group.length})
              </span>
              {group.map((r) => (
                <RequestCard key={r.id} request={r} onSetStatus={setStatus} onOpen={onOpen} />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RequestCard({
  request,
  onSetStatus,
  onOpen,
}: {
  request: ClipRequest;
  onSetStatus: (id: string, status: string) => void;
  onOpen?: (request: ClipRequest) => void;
}) {
  return (
    <div
      onClick={() => onOpen?.(request)}
      style={{
        borderRadius: "var(--r-sm)",
        background: "var(--bg-surface)",
        border: `1px solid ${request.status === "pending" ? "rgba(251,191,36,0.3)" : "var(--border-base)"}`,
        padding: 14,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        cursor: onOpen ? "pointer" : "default",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ padding: "1px 6px", borderRadius: 4, background: "rgba(0,0,0,0.3)", color: STATUS_COLOR[request.status], fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700 }}>
          {STATUS_LABEL[request.status] ?? request.status.toUpperCase()}
        </span>
        <span style={{ flex: 1, color: "var(--text-primary)", fontSize: 15, fontWeight: 600 }}>
          {request.operator} · {request.storage}
        </span>
        <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{request.supervisor_host}</span>
      </div>
      <div style={{ color: "var(--accent-primary)", fontFamily: "var(--font-mono)", fontSize: 14 }}>
        {request.start_time} → {request.end_time}
      </div>
      {request.description && <p style={{ color: "var(--text-muted)", fontSize: 14 }}>{request.description}</p>}
      {request.status !== "done" && request.status !== "declined" && (
        <div style={{ display: "flex", gap: 8 }}>
          {request.status === "pending" && (
            <>
              <button type="button" onClick={(e) => { e.stopPropagation(); onSetStatus(request.id, "processing"); }} style={actionBtnStyle("var(--accent-primary)")}>
                Marcar procesando
              </button>
              <button type="button" onClick={(e) => { e.stopPropagation(); onSetStatus(request.id, "declined"); }} style={actionBtnStyle("var(--accent-record)")}>
                Declinar
              </button>
            </>
          )}
          <button type="button" onClick={(e) => { e.stopPropagation(); onSetStatus(request.id, "done"); }} style={actionBtnStyle("var(--accent-ok)")}>
            Marcar listo
          </button>
        </div>
      )}
    </div>
  );
}

function actionBtnStyle(color: string) {
  return {
    height: 30,
    padding: "0 14px",
    borderRadius: "var(--r-sm)",
    border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
    background: `color-mix(in srgb, ${color} 10%, transparent)`,
    color,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  } as const;
}
