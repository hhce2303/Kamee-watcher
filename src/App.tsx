import { useEffect } from "react";
import AppShell from "./shell/AppShell";
import RoleSetupWizard from "./features/settings/RoleSetupWizard";
import MiniMode from "./features/mini/MiniMode";
import ITEditorView from "./features/it/ITEditorView";
import { initAppStore, useAppStore } from "./stores/appStore";

const isMiniWindow = new URLSearchParams(window.location.search).get("window") === "mini";

/**
 * Role-aware root, mirroring qml/Main.qml's role branching:
 *   ?window=mini  → the floating MiniMode widget (its own Tauri window)
 *   role === ""   → RoleSetupWizard (first-run role picker)
 *   role === "it" → full-screen IT dashboard (ITEditorView — M9)
 *   else          → the tabbed shell (AppShell)
 */
export default function App() {
  const settings = useAppStore((s) => s.settings);

  useEffect(() => initAppStore(), []);

  if (isMiniWindow) {
    return <MiniMode />;
  }

  if (settings === null) {
    return (
      <div className="placeholder-tab" style={{ height: "100vh" }}>
        <p>Connecting to backend…</p>
      </div>
    );
  }

  if (settings.role === "") {
    return <RoleSetupWizard />;
  }

  if (settings.role === "it") {
    return <ITEditorView />;
  }

  return <AppShell />;
}
