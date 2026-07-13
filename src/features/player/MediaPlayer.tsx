import { useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-shell";
import { clipUrl } from "../../lib/mediaUrl";
import { useClipTranscode } from "../../hooks/useClipTranscode";

interface MediaPlayerProps {
  path: string;
}

/**
 * Clip playback via the `watcher://` custom protocol (Range-streamable).
 *
 * TD-1: WebView2 has no software HEVC fallback — if the browser reports
 * MEDIA_ERR_SRC_NOT_SUPPORTED, offer an on-demand H.264 transcode or opening
 * the file in the system's default player.
 *
 * TD-7: `<video>.currentTime` is wall-clock time, not frame-exact — this
 * player is for review only; trims/exports are computed and rendered
 * server-side (EditorApi/FFmpeg), never from values read here.
 */
export default function MediaPlayer({ path }: MediaPlayerProps) {
  const [unsupported, setUnsupported] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const transcode = useClipTranscode();

  const activePath = transcode.outputPath ?? path;

  function handleError() {
    const err = videoRef.current?.error;
    if (err?.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED) {
      setUnsupported(true);
    }
  }

  function handleFullscreen() {
    void videoRef.current?.requestFullscreen();
  }

  if (unsupported && !transcode.outputPath) {
    return (
      <div className="placeholder-tab" style={{ gap: 12 }}>
        <h2>Formato no soportado</h2>
        <p>Este clip usa un códec que WebView2 no puede reproducir en este equipo.</p>
        {transcode.transcoding ? (
          <p style={{ fontFamily: "var(--font-mono)" }}>Convirtiendo… {(transcode.progress * 100).toFixed(0)}%</p>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={() => transcode.start(path)} style={actionBtnStyle}>
              Convertir a H.264
            </button>
            <button type="button" onClick={() => void open(path)} style={actionBtnStyle}>
              Abrir externo
            </button>
          </div>
        )}
        {transcode.error && <p style={{ color: "var(--accent-record)", fontSize: 12 }}>{transcode.error}</p>}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption -- desktop-capture
          footage has no dialogue/narration track to caption; this is a review
          player (TD-7), not a content-consumption player. */}
      <video
        ref={videoRef}
        key={activePath}
        src={clipUrl(activePath)}
        controls
        onError={handleError}
        style={{ width: "100%", maxHeight: "70vh", background: "var(--video-bg)", borderRadius: "var(--r-md)" }}
      />
      <button type="button" onClick={handleFullscreen} style={{ ...actionBtnStyle, alignSelf: "flex-start" }}>
        Pantalla completa
      </button>
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
