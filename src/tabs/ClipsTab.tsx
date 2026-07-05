import { useEffect, useState } from "react";
import { useIpc } from "../hooks/useIpc";
import { useTauriEvent } from "../hooks/useTauriEvent";
import type { ClipDTO } from "../types/dto";

export default function ClipsTab() {
  const { send } = useIpc();
  const [clips, setClips] = useState<ClipDTO[]>([]);

  useEffect(() => {
    send<ClipDTO[]>("list_clips").then(setClips).catch(console.error);
  }, []);

  useTauriEvent<ClipDTO[]>("ClipsChanged", (ev) => setClips(ev));

  if (clips.length === 0) {
    return (
      <div className="placeholder-tab">
        <h2>No clips yet</h2>
        <p>Clips will appear here once recording events have been saved.</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
      <p style={{ color: "var(--text-muted)", fontSize: 11, marginBottom: "var(--sp-2)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {clips.length} clip{clips.length !== 1 ? "s" : ""}
      </p>
      {clips.map((clip) => (
        <div
          key={clip.path}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--sp-4)",
            padding: "var(--sp-3) var(--sp-4)",
            background: "var(--bg-surface)",
            borderRadius: "var(--r-md)",
            border: "1px solid var(--border-base)",
          }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: clip.is_event ? "var(--accent-record)" : "var(--text-dim)",
              flexShrink: 0,
            }}
          />
          <span style={{ flex: 1, fontWeight: 500, fontSize: 13 }}>{clip.clip_name}</span>
          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{clip.size_label}</span>
          <span style={{ color: "var(--text-dim)", fontSize: 12 }}>{clip.date_label}</span>
        </div>
      ))}
    </div>
  );
}
