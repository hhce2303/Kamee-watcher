import { useState } from "react";
import { useTauriEvent } from "./hooks/useTauriEvent";
import RecordingTab from "./tabs/RecordingTab";
import ClipsTab from "./tabs/ClipsTab";
import AnalyticsTab from "./tabs/AnalyticsTab";
import SettingsTab from "./tabs/SettingsTab";

type Tab = "recording" | "clips" | "analytics" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "recording", label: "Recording" },
  { id: "clips",     label: "Clips" },
  { id: "analytics", label: "Analytics" },
  { id: "settings",  label: "Settings" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("recording");
  const [ipcConnected, setIpcConnected] = useState(false);

  useTauriEvent("ipc_connected",    () => setIpcConnected(true));
  useTauriEvent("ipc_disconnected", () => setIpcConnected(false));

  return (
    <div className="app">
      <nav className="tab-bar">
        <span className="tab-bar__logo">THE WATCHER</span>
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
        <span className="ipc-badge">
          <span className={`ipc-badge__dot ${ipcConnected ? "connected" : ""}`} />
          {ipcConnected ? "Backend connected" : "Backend disconnected"}
        </span>
      </nav>

      <main className="tab-content">
        {tab === "recording" && <RecordingTab />}
        {tab === "clips"     && <ClipsTab />}
        {tab === "analytics" && <AnalyticsTab />}
        {tab === "settings"  && <SettingsTab />}
      </main>
    </div>
  );
}
