import { useEffect } from "react";
import WHotkey from "../components/WHotkey";
import { isTabVisible, type RolePolicy } from "../lib/policy";
import { useAppStore } from "../stores/appStore";

interface Tab {
  index: number;
  label: string;
  hotkey?: string[];
}

// Indices 0-3 mirror qml/Main.qml's tab order exactly; Analytics (4) has no
// QML counterpart — it's a React-only addition from Fase 5.
const TABS: Tab[] = [
  { index: 0, label: "Grabación", hotkey: ["Ctrl", "1"] },
  { index: 1, label: "Clips", hotkey: ["Ctrl", "2"] },
  { index: 2, label: "Mini-modo", hotkey: ["Ctrl", "3"] },
  { index: 3, label: "Ajustes", hotkey: ["Ctrl", "4"] },
  { index: 4, label: "Analytics" },
];

interface TabBarProps {
  policy: RolePolicy;
}

export default function TabBar({ policy }: TabBarProps) {
  const activeTab = useAppStore((s) => s.activeTab);
  const setActiveTab = useAppStore((s) => s.setActiveTab);
  const visible = TABS.filter((t) => isTabVisible(policy, t.index));

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!e.ctrlKey) return;
      const n = Number(e.key);
      if (n >= 1 && n <= 4) {
        const idx = n - 1;
        if (isTabVisible(policy, idx)) {
          e.preventDefault();
          setActiveTab(idx);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [policy, setActiveTab]);

  return (
    <nav className="tab-bar">
      <span className="tab-bar__logo">THE WATCHER</span>
      {visible.map((tab) => (
        <button
          key={tab.index}
          className={activeTab === tab.index ? "active" : ""}
          onClick={() => setActiveTab(tab.index)}
          title={tab.hotkey ? tab.hotkey.join("+") : undefined}
        >
          {tab.label}
        </button>
      ))}
      <span className="ipc-badge">
        <ConnectionDot />
      </span>
    </nav>
  );
}

function ConnectionDot() {
  const connected = useAppStore((s) => s.ipcConnected);
  return (
    <>
      <span className={`ipc-badge__dot ${connected ? "connected" : ""}`} />
      {connected ? "Backend connected" : "Backend disconnected"}
    </>
  );
}

// Re-exported so SettingsView (M6) can show real hotkey chips for the same tabs.
export { TABS as SHELL_TABS };
export function ShellHotkey({ tabIndex }: { tabIndex: number }) {
  const tab = TABS.find((t) => t.index === tabIndex);
  return tab?.hotkey ? <WHotkey keys={tab.hotkey} /> : null;
}
