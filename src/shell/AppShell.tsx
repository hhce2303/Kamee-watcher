import { getCurrentWindow } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import RecordingView from "../features/recording/RecordingView";
import ClipsView from "../features/clips/ClipsView";
import SupervisorView from "../features/supervisor/SupervisorView";
import AnalyticsTab from "../tabs/AnalyticsTab";
import SettingsView from "../features/settings/SettingsView";
import { useAppStore } from "../stores/appStore";
import TabBar from "./TabBar";
import Statusbar from "./Statusbar";
import LogDrawer from "./LogDrawer";
import HealthBadge from "./HealthBadge";
import WindowControls from "./WindowControls";

/** Role-gated tab shell for operator/supervisor roles (IT gets ITEditorView — M9). */
export default function AppShell() {
  const activeTab = useAppStore((s) => s.activeTab);
  const policy = useAppStore((s) => s.policy);
  const role = useAppStore((s) => s.settings?.role);

  return (
    <div className="app">
      <div style={{ display: "flex", alignItems: "center" }}>
        <TabBar policy={policy} />
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-5)", padding: "0 var(--sp-5)" }}>
          <HealthBadge />
          <WindowControls policy={policy} />
        </div>
      </div>
      <main className="tab-content">
        {activeTab === 0 && <RecordingView />}
        {activeTab === 1 && (role === "supervisor" ? <SupervisorView /> : <ClipsView />)}
        {activeTab === 2 && <MiniModeLauncher onLaunched={() => useAppStore.getState().setActiveTab(0)} />}
        {activeTab === 3 && <SettingsView />}
        {activeTab === 4 && <AnalyticsTab />}
      </main>
      {/* Absolutely positioned (see .log-drawer in App.css) — never shares layout flow with
          .tab-content, so it can never push the tabs or content around. */}
      <LogDrawer />
      <Statusbar />
    </div>
  );
}

/** Ctrl+3 / tab launcher: shows the floating mini window, hides the main one. */
function MiniModeLauncher({ onLaunched }: { onLaunched: () => void }) {
  async function launch() {
    const mini = await WebviewWindow.getByLabel("mini");
    await mini?.show();
    await mini?.setFocus();
    await getCurrentWindow().hide();
    onLaunched();
  }

  return (
    <div className="placeholder-tab">
      <h2>Mini-modo</h2>
      <p>Widget flotante siempre-encima con el estado de grabación y el botón de marcar evento.</p>
      <button
        type="button"
        onClick={() => void launch()}
        style={{ height: 36, padding: "0 20px", borderRadius: "var(--r-sm)", border: "none", background: "var(--accent-primary)", color: "var(--bg-base)", fontSize: 14, fontWeight: 600, cursor: "pointer" }}
      >
        Activar mini-modo
      </button>
    </div>
  );
}
