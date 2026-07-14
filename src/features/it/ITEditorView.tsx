import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "../../stores/appStore";
import { useInboxRequests } from "../../hooks/useInboxRequests";
import { useEditorTimeline } from "../../hooks/useEditorTimeline";
import { useSettingsForm } from "../../hooks/useSettingsForm";
import ClipBrowser from "../clips/ClipBrowser";
import VideoEditorView from "../editor/VideoEditorView";
import PrivateSavePanel from "../delivery/PrivateSavePanel";
import RecordingView from "../recording/RecordingView";
import SettingsView from "../settings/SettingsView";
import ITInboxPanel from "./ITInboxPanel";
import { ITHealthChips } from "../../shell/HealthChips";
import PinUnlockPrompt from "../../components/PinUnlockPrompt";
import CollapsiblePanel from "../../components/CollapsiblePanel";
import type { ClipRequest } from "../../types/dto";

type View = "cola" | "editor" | "grabacion" | "entregas" | "ajustes";

const NAV: { id: View; label: string; icon: string }[] = [
  { id: "cola", label: "Cola", icon: "☰" },
  { id: "editor", label: "Editor", icon: "✂" },
  { id: "grabacion", label: "Grabación", icon: "●" },
  { id: "entregas", label: "Entregas", icon: "☁" },
  { id: "ajustes", label: "Ajustes", icon: "⚙" },
];

/**
 * IT dashboard shell — port of qml/ITEditorView.qml. Full-screen root for the
 * IT role (App.tsx renders this instead of AppShell when settings.role === "it").
 */
export default function ITEditorView() {
  const [view, setView] = useState<View>("cola");
  const [now, setNow] = useState(() => new Date());
  const itUnlocked = useAppStore((s) => s.settings?.it_unlocked ?? false);
  const { requests, setStatus } = useInboxRequests();
  const editor = useEditorTimeline();

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  async function openRequestInEditor(req: ClipRequest) {
    if (req.status === "pending") await setStatus(req.id, "processing");
    setView("editor");
  }

  async function loadFilesIntoReel() {
    const picked = await open({
      multiple: true,
      filters: [{ name: "Videos", extensions: ["mp4", "mkv", "mov", "avi", "ts", "m4v", "webm"] }],
    });
    const paths = Array.isArray(picked) ? picked : picked ? [picked] : [];
    if (paths.length > 0) await editor.actions.addFiles(paths);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg-base)" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 14, height: 52, padding: "0 20px", borderBottom: "1px solid var(--border-base)", flexShrink: 0 }}>
        <span style={{ color: "var(--accent-primary)", fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: "1.5px" }}>THE WATCHER · IT</span>
        <div style={{ flex: 1 }} />
        <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
          {now.toLocaleDateString("es-MX", { day: "2-digit", month: "short", year: "numeric" })} · {now.toLocaleTimeString("es-MX")}
        </span>
        <ITHealthChips />
      </header>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <nav style={{ width: 200, flexShrink: 0, borderRight: "1px solid var(--border-base)", padding: "12px 0" }}>
          {NAV.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => setView(n.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                width: "100%",
                height: 38,
                padding: "0 20px",
                border: "none",
                borderLeft: `2px solid ${view === n.id ? "var(--accent-primary)" : "transparent"}`,
                background: view === n.id ? "var(--primary-dim)" : "transparent",
                color: view === n.id ? "var(--accent-primary)" : "var(--text-muted)",
                fontSize: 14,
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span>{n.icon}</span>
              <span>{n.label}</span>
            </button>
          ))}
        </nav>

        <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", padding: 20, minWidth: 0 }}>
          {view === "cola" && (
            <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
              <ITInboxPanel onOpen={openRequestInEditor} />
            </div>
          )}

          {view === "editor" && (
            <div style={{ display: "flex", gap: 14, flex: 1, minHeight: 0 }}>
              <CollapsiblePanel side="left" label="UBICACIONES" icon="◈" width={340}>
                <button type="button" onClick={() => void loadFilesIntoReel()} style={loadFilesBtnStyle}>
                  + Cargar videos
                </button>
                <div style={{ flex: 1, minHeight: 0 }}>
                  {/* addFiles probes duration server-side (unlike addClip, which needs a
                      caller-supplied duration) — the right call for "pick from NAS/local". */}
                  <ClipBrowser onPlay={(path) => void editor.actions.addFiles([path])} />
                </div>
              </CollapsiblePanel>
              <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                <VideoEditorView defaultOutputPath="reel.mp4" />
              </div>
              <CollapsiblePanel side="right" label="ONEDRIVE" icon="☁" width={280}>
                <div style={{ overflowY: "auto" }}>
                  <PrivateSavePanel />
                </div>
              </CollapsiblePanel>
            </div>
          )}

          {view === "grabacion" && (
            <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
              <RecordingView />
            </div>
          )}

          {view === "entregas" && (
            <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              <DeliveredList requests={requests.filter((r) => r.status === "done")} />
            </div>
          )}

          {view === "ajustes" && (
            <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
              {itUnlocked ? <SettingsView /> : <AjustesPinGate />}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function AjustesPinGate() {
  const { actions } = useSettingsForm();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 320 }}>
      <p style={{ color: "var(--text-muted)", fontSize: 14 }}>Ingresa el PIN de IT para acceder a ajustes.</p>
      <PinUnlockPrompt onUnlock={actions.unlockIt} />
    </div>
  );
}

function DeliveredList({ requests }: { requests: ClipRequest[] }) {
  if (requests.length === 0) {
    return <p style={{ color: "var(--text-dim)", fontSize: 14 }}>Sin entregas todavía.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 640 }}>
      {requests.map((r) => (
        <div key={r.id} style={{ borderRadius: "var(--r-sm)", background: "var(--bg-surface)", border: "1px solid var(--border-base)", padding: 14 }}>
          <div style={{ color: "var(--text-primary)", fontSize: 15, fontWeight: 600 }}>{r.operator} — {r.storage}</div>
          <div style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 13 }}>{r.start_time} → {r.end_time}</div>
        </div>
      ))}
    </div>
  );
}

const loadFilesBtnStyle = {
  height: 34,
  borderRadius: "var(--r-sm)",
  border: "1px dashed var(--border-subtle)",
  background: "transparent",
  color: "var(--text-muted)",
  fontSize: 13,
  cursor: "pointer",
} as const;
