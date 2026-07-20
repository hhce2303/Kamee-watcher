import { useState } from "react";
import ClipBrowser from "./ClipBrowser";
import MediaPlayer from "../player/MediaPlayer";

/** Clips tab — browser + player, replaces the old flat-list ClipsTab. */
export default function ClipsView() {
  const [playingPath, setPlayingPath] = useState<string | null>(null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-5)", height: "100%" }}>
      {playingPath && (
        <div>
          <MediaPlayer path={playingPath} />
          <button
            type="button"
            onClick={() => setPlayingPath(null)}
            style={{ marginTop: 8, background: "transparent", border: "none", color: "var(--text-muted)", fontSize: 13, cursor: "pointer" }}
          >
            ← Volver al explorador
          </button>
        </div>
      )}
      <div style={{ flex: 1, display: playingPath ? "none" : "flex", minHeight: 0 }}>
        <ClipBrowser onPlay={setPlayingPath} />
      </div>
    </div>
  );
}
