import type { RefObject } from "react";
import { clipUrl } from "../../lib/mediaUrl";
import TrimHandles from "./TrimHandles";
import type { ClipEntryDTO } from "../../types/dto";

interface EditorTransportProps {
  entry: ClipEntryDTO | null;
  onTrim: (inPointS: number, outPointS: number) => void;
  videoRef: RefObject<HTMLVideoElement>;
}

/** Preview + trim controls for the selected reel clip — port of VideoEditor.qml's transport. */
export default function EditorTransport({ entry, onTrim, videoRef }: EditorTransportProps) {
  if (!entry) {
    return (
      <div className="placeholder-tab">
        <p>Selecciona un clip de la línea de tiempo para previsualizarlo.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <video
        key={entry.source_path}
        ref={videoRef}
        src={clipUrl(entry.source_path)}
        controls
        style={{ width: "100%", maxHeight: "45vh", background: "#000", borderRadius: "var(--r-md)" }}
      />
      <TrimHandles
        sourceDurationS={entry.source_duration_s}
        inPointS={entry.in_point_s}
        outPointS={entry.out_point_s}
        onCommit={onTrim}
      />
    </div>
  );
}
