import { open } from "@tauri-apps/plugin-shell";

interface UnsupportedCodecFallbackProps {
  path: string;
  transcoding: boolean;
  progress: number;
  error: string | null;
  onConvert: () => void;
  onCancel: () => void;
}

/**
 * "Formato no soportado" recovery UI — TD-1: WebView2 has no software HEVC
 * decoder, and some containers (e.g. a raw/interrupted MKV) aren't
 * recognized at all. Shared by MediaPlayer.tsx (Clips tab) and
 * EditorTransport.tsx (IT editor) so both offer the same
 * convert/cancel/open-externally recovery instead of two copies drifting.
 */
export default function UnsupportedCodecFallback({
  path,
  transcoding,
  progress,
  error,
  onConvert,
  onCancel,
}: UnsupportedCodecFallbackProps) {
  return (
    <div className="placeholder-tab" style={{ gap: 12, flex: 1, minHeight: 0 }}>
      <h2>Formato no soportado</h2>
      <p>Este clip usa un códec que WebView2 no puede reproducir en este equipo.</p>
      {transcoding ? (
        <>
          <p style={{ fontFamily: "var(--font-mono)" }}>Convirtiendo… {(progress * 100).toFixed(0)}%</p>
          <button type="button" onClick={onCancel} style={actionBtnStyle}>
            Cancelar
          </button>
        </>
      ) : (
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" onClick={onConvert} style={actionBtnStyle}>
            Convertir a H.264
          </button>
          <button type="button" onClick={() => void open(path)} style={actionBtnStyle}>
            Abrir externo
          </button>
        </div>
      )}
      {error && <p style={{ color: "var(--accent-record)", fontSize: 12 }}>{error}</p>}
    </div>
  );
}

const actionBtnStyle = {
  height: 32,
  padding: "0 16px",
  borderRadius: "var(--r-sm)",
  border: "1px solid var(--border-subtle)",
  background: "var(--bg-surface)",
  color: "var(--text-primary)",
  fontSize: 13,
  cursor: "pointer",
} as const;
