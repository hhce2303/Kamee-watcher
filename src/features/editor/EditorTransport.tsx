import { useState } from "react";
import type { RefObject } from "react";
import { clipUrl } from "../../lib/mediaUrl";
import { useClipTranscode } from "../../hooks/useClipTranscode";
import TrimHandles from "./TrimHandles";
import ZoomOverlay from "../../components/ZoomOverlay";
import UnsupportedCodecFallback from "../../components/UnsupportedCodecFallback";
import { useFrameZoom } from "../../hooks/useFrameZoom";
import type { ClipEntryDTO } from "../../types/dto";

interface EditorTransportProps {
  entry: ClipEntryDTO | null;
  onTrim: (inPointS: number, outPointS: number) => void;
  videoRef: RefObject<HTMLVideoElement>;
}

/**
 * Preview + trim controls for the selected reel clip — port of
 * VideoEditor.qml's transport. Mount this with `key={entry.source_path}` from
 * the parent (see VideoEditorView) so switching clips gets a clean remount —
 * zoom, the codec-fallback below, and TrimHandles' own edit state must never
 * leak from one clip to the next.
 */
export default function EditorTransport({ entry, onTrim, videoRef }: EditorTransportProps) {
  const frameZoom = useFrameZoom(entry?.source_path ?? null);
  const [unsupported, setUnsupported] = useState(false);
  const transcode = useClipTranscode();

  if (!entry) {
    return (
      <div className="placeholder-tab">
        <p>Selecciona un clip de la línea de tiempo para previsualizarlo.</p>
      </div>
    );
  }

  // TD-1: WebView2 has no software HEVC fallback — a video stuck at frame 0
  // with no error text is that failure mode, same as MediaPlayer.tsx's Clips
  // tab. Offer the same on-demand H.264 transcode / open-externally escape.
  const activePath = transcode.outputPath ?? entry.source_path;

  function handleError() {
    const err = videoRef.current?.error;
    if (err?.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED) {
      setUnsupported(true);
    }
  }

  if (unsupported && !transcode.outputPath) {
    return (
      <UnsupportedCodecFallback
        path={entry.source_path}
        transcoding={transcode.transcoding}
        progress={transcode.progress}
        error={transcode.error}
        onConvert={() => transcode.start(entry.source_path)}
        onCancel={() => transcode.cancel(entry.source_path)}
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1, minHeight: 0 }}>
      <div
        style={{ position: "relative", overflow: "hidden", borderRadius: "var(--r-md)", flex: 1, minHeight: 0 }}
        onWheel={frameZoom.handlers.onWheel}
        onPointerDown={frameZoom.handlers.onPointerDown}
        onPointerMove={frameZoom.handlers.onPointerMove}
        onPointerUp={frameZoom.handlers.onPointerUp}
      >
        {/* eslint-disable-next-line jsx-a11y/media-has-caption -- desktop-capture
            footage has no dialogue/narration track to caption; this is a trim/
            review player, not a content-consumption player. */}
        <video
          key={activePath}
          ref={videoRef}
          src={clipUrl(activePath)}
          controls
          draggable={false}
          onError={handleError}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            background: "var(--video-bg)",
            display: "block",
            transform: frameZoom.transformCss,
            transformOrigin: "center",
            cursor: frameZoom.isZoomed ? (frameZoom.isDragging ? "grabbing" : "grab") : "default",
          }}
        />
        <ZoomOverlay zoom={frameZoom.zoom} onReset={frameZoom.reset} />
      </div>
      <TrimHandles
        sourceDurationS={entry.source_duration_s}
        inPointS={entry.in_point_s}
        outPointS={entry.out_point_s}
        onCommit={onTrim}
      />
    </div>
  );
}
