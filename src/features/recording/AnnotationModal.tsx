import { useState, type CSSProperties, type ReactNode } from "react";
import Modal from "../../components/Modal";
import WSeg from "../../components/WSeg";

const PRESET_TAGS = ["crash", "lag", "auth error", "memory leak", "session drop", "ui glitch"];
const SEVERITIES = [
  { value: "low", label: "Baja", color: "var(--accent-ok)" },
  { value: "medium", label: "Media", color: "var(--accent-yellow)" },
  { value: "high", label: "Alta", color: "var(--accent-record)" },
] as const;

interface AnnotationModalProps {
  eventTimecode: string;
  onSaved: (tag: string, severity: string, note: string) => void;
  onSkipped: () => void;
}

/**
 * Event tagging form shown after the pre-roll countdown — port of
 * qml/AnnotationModal.qml. UI-only, like the QML original: nothing is
 * persisted server-side (see main.py Main.qml:938 `eventCount += 1`).
 */
export default function AnnotationModal({ eventTimecode, onSaved, onSkipped }: AnnotationModalProps) {
  const [tag, setTag] = useState("");
  const [severity, setSeverity] = useState<string>("medium");
  const [note, setNote] = useState("");

  function save() {
    onSaved(tag.trim() || "sin etiqueta", severity, note);
  }

  return (
    <Modal onClose={onSkipped}>
      <div style={{ width: 440, display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 14, borderBottom: "1px solid var(--border-base)" }}>
          <span style={{ width: 6, height: 6, borderRadius: 3, background: "var(--accent-yellow)" }} />
          <span style={{ color: "var(--text-primary)", fontSize: 15, fontWeight: 600 }}>Evento marcado</span>
          <div style={{ flex: 1 }} />
          <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 13 }}>T+{eventTimecode}</span>
        </div>

        <FormField label="ETIQUETA">
          <input
            autoFocus
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            placeholder="ej. crash en checkout"
            style={inputStyle}
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {PRESET_TAGS.map((preset) => {
              const selected = tag === preset;
              return (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setTag(preset)}
                  style={{
                    padding: "3px 10px",
                    borderRadius: "var(--r-pill)",
                    background: selected ? "var(--primary-dim)" : "transparent",
                    border: `1px solid ${selected ? "var(--accent-primary)" : "var(--border-base)"}`,
                    color: selected ? "var(--accent-primary)" : "var(--text-muted)",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {preset}
                </button>
              );
            })}
          </div>
        </FormField>

        <FormField label="SEVERIDAD">
          <WSeg options={SEVERITIES.map((s) => ({ value: s.value, label: s.label }))} value={severity} onSelect={setSeverity} />
        </FormField>

        <FormField label="NOTA (OPCIONAL)">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Contexto adicional…"
            rows={3}
            style={{ ...inputStyle, resize: "vertical", fontFamily: "var(--font-sans)" }}
          />
        </FormField>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: 36,
            padding: "0 12px",
            borderRadius: "var(--r-sm)",
            background: "var(--bg-base)",
            border: "1px solid var(--border-base)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
          }}
        >
          <span style={{ color: "var(--text-muted)", letterSpacing: "0.8px" }}>CLIP FINAL · 4 MIN</span>
          <span style={{ display: "flex", gap: 8 }}>
            <span style={{ color: "var(--accent-primary)" }}>−2:00 pre</span>
            <span style={{ color: "var(--border-subtle)" }}>│</span>
            <span style={{ color: "var(--accent-record)", fontWeight: 700 }}>● EVENT</span>
            <span style={{ color: "var(--border-subtle)" }}>│</span>
            <span style={{ color: "var(--accent-primary)" }}>+2:00 post</span>
          </span>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, paddingTop: 14, borderTop: "1px solid var(--border-base)" }}>
          <button type="button" onClick={onSkipped} style={secondaryBtnStyle}>
            Sin etiqueta
          </button>
          <button type="button" onClick={save} style={primaryBtnStyle}>
            Guardar evento ↵
          </button>
        </div>
      </div>
    </Modal>
  );
}

function FormField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ color: "var(--text-muted)", fontSize: 11, fontWeight: 600, letterSpacing: "1.4px" }}>{label}</span>
      {children}
    </div>
  );
}

const inputStyle: CSSProperties = {
  width: "100%",
  height: 36,
  padding: "0 12px",
  borderRadius: "var(--r-sm)",
  background: "var(--bg-base)",
  border: "1px solid var(--border-base)",
  color: "var(--text-primary)",
  fontFamily: "var(--font-sans)",
  fontSize: 14,
};

const secondaryBtnStyle: CSSProperties = {
  height: 32,
  padding: "0 16px",
  borderRadius: "var(--r-sm)",
  background: "transparent",
  border: "1px solid var(--border-base)",
  color: "var(--text-muted)",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const primaryBtnStyle: CSSProperties = {
  height: 32,
  padding: "0 22px",
  borderRadius: "var(--r-sm)",
  background: "var(--accent-primary)",
  border: "none",
  color: "var(--bg-base)",
  fontSize: 13,
  fontWeight: 700,
  cursor: "pointer",
};
