import { useClipBrowser } from "../../hooks/useClipBrowser";
import { useMediaRoots } from "../../hooks/useMediaRoots";
import type { BrowseEntry } from "../../types/dto";

interface ClipBrowserProps {
  onPlay: (path: string) => void;
}

const LOCATIONS = (nasRoot: string) => [
  { icon: "◈", label: "SIG-SLC-Storage", path: nasRoot },
  { icon: "▤", label: "Clips combinados", path: "LOCAL_CLIPS" },
  { icon: "▦", label: "Clips por pantalla", path: "LOCAL_RAW" },
];

/** Folder navigation for the Clips tab — port of qml/ClipBrowser.qml. */
export default function ClipBrowser({ onPlay }: ClipBrowserProps) {
  const b = useClipBrowser();
  const { roots } = useMediaRoots();
  const nasRoot = roots?.storage_roots[0] ?? "";
  const currentRoot = b.navStack[0]?.path;

  return (
    <div style={{ display: "flex", height: "100%", border: "1px solid var(--border-base)", borderRadius: "var(--r-md)", overflow: "hidden" }}>
      <aside style={{ width: 210, flexShrink: 0, background: "var(--bg-surface)", borderRight: "1px solid var(--border-base)", padding: "16px 0" }}>
        <SideLabel text="UBICACIONES" />
        {LOCATIONS(nasRoot).map((loc) => (
          <SideEntry
            key={loc.path}
            icon={loc.icon}
            label={loc.label}
            active={currentRoot === loc.path}
            onClick={() => loc.path && b.openLocation(loc.label, loc.path)}
          />
        ))}
      </aside>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <Toolbar navStack={b.navStack} onCrumb={b.goToCrumb} onRoot={b.goBack} onReload={b.reload} canBack={b.navStack.length > 0} />
        <FileList browser={b} onPlay={onPlay} nasRoot={nasRoot} />
        <StatusBar selected={b.selected} count={b.items.length} onPlay={onPlay} />
      </div>
    </div>
  );
}

function SideLabel({ text }: { text: string }) {
  return <div style={{ padding: "0 16px 6px", color: "var(--text-dim)", fontSize: 11, fontWeight: 700, letterSpacing: "1.2px" }}>{text}</div>;
}

function SideEntry({ icon, label, active, onClick }: { icon: string; label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        height: 34,
        padding: "0 16px",
        border: "none",
        borderLeft: `2px solid ${active ? "var(--accent-primary)" : "transparent"}`,
        background: active ? "var(--primary-dim)" : "transparent",
        color: active ? "var(--accent-primary)" : "var(--text-muted)",
        fontSize: 14,
        cursor: "pointer",
        textAlign: "left",
      }}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function Toolbar({
  navStack,
  onCrumb,
  onRoot,
  onReload,
  canBack,
}: {
  navStack: { label: string; path: string }[];
  onCrumb: (i: number) => void;
  onRoot: () => void;
  onReload: () => void;
  canBack: boolean;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, height: 46, padding: "0 10px", borderBottom: "1px solid var(--border-base)" }}>
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          height: 30,
          padding: "0 12px",
          borderRadius: "var(--r-xs)",
          background: "rgba(0,0,0,0.28)",
          border: "1px solid var(--border-base)",
          fontSize: 14,
          gap: 4,
          overflow: "hidden",
        }}
      >
        <span
          onClick={onRoot}
          style={{ color: navStack.length === 0 ? "var(--text-primary)" : "var(--accent-primary)", cursor: "pointer" }}
        >
          ⊛ Red
        </span>
        {navStack.map((c, i) => (
          <span key={c.path} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ color: "var(--text-dim)" }}>›</span>
            <span
              onClick={() => i < navStack.length - 1 && onCrumb(i)}
              style={{
                color: i === navStack.length - 1 ? "var(--text-primary)" : "var(--accent-primary)",
                cursor: i === navStack.length - 1 ? "default" : "pointer",
              }}
            >
              {c.label}
            </span>
          </span>
        ))}
      </div>
      <button type="button" disabled={!canBack} onClick={onReload} title="Recargar" style={navBtnStyle}>
        ⟳
      </button>
    </div>
  );
}

function FileList({ browser: b, onPlay, nasRoot }: { browser: ReturnType<typeof useClipBrowser>; onPlay: (path: string) => void; nasRoot: string }) {
  if (b.loading) {
    return <Centered>Conectando a {nasRoot || "el almacenamiento"}…</Centered>;
  }
  if (b.failed && b.items.length === 0) {
    return (
      <Centered>
        <div>Sin conexión a {nasRoot}</div>
        <button type="button" onClick={b.reload} style={{ ...navBtnStyle, width: "auto", padding: "0 16px", marginTop: 12 }}>
          ⟳ Reintentar
        </button>
      </Centered>
    );
  }
  if (b.items.length === 0) {
    return <Centered>{b.navStack.length === 0 ? "Selecciona una ubicación" : "Esta carpeta está vacía"}</Centered>;
  }
  return (
    <div style={{ flex: 1, overflow: "auto" }}>
      {b.items.map((item) => (
        <FileRow key={item.path} item={item} selected={b.selected?.path === item.path} onSelect={b.select} onOpen={b.openItem} onPlay={onPlay} />
      ))}
    </div>
  );
}

function FileRow({
  item,
  selected,
  onSelect,
  onOpen,
  onPlay,
}: {
  item: BrowseEntry;
  selected: boolean;
  onSelect: (e: BrowseEntry) => void;
  onOpen: (e: BrowseEntry) => void;
  onPlay: (path: string) => void;
}) {
  return (
    <div
      onClick={() => onSelect(item)}
      onDoubleClick={() => (item.is_dir ? onOpen(item) : onPlay(item.path))}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        height: 42,
        padding: "0 14px",
        borderBottom: "1px solid var(--border-base)",
        background: selected ? "rgba(56,189,248,0.10)" : "transparent",
        cursor: "pointer",
        fontFamily: "var(--font-mono)",
        fontSize: 13,
      }}
    >
      <span style={{ color: item.is_dir ? "var(--text-dim)" : "var(--accent-primary)" }}>{item.is_dir ? "▸" : "▶"}</span>
      <span style={{ flex: 1, color: item.is_dir ? "var(--text-primary)" : "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {item.name}
      </span>
      <span style={{ color: "var(--text-dim)", fontSize: 12 }}>{item.modified || "—"}</span>
      <span style={{ color: "var(--text-dim)", fontSize: 12, width: 60, textAlign: "right" }}>{item.is_dir ? "—" : item.size || "—"}</span>
    </div>
  );
}

function StatusBar({ selected, count, onPlay }: { selected: BrowseEntry | null; count: number; onPlay: (path: string) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, height: 36, padding: "0 16px", borderTop: "1px solid var(--border-base)", background: "var(--bg-surface)" }}>
      <span style={{ flex: 1, color: selected ? "var(--text-primary)" : "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {selected ? `${selected.is_dir ? "▸" : "▶"} ${selected.name}` : count > 0 ? `${count} elemento(s)` : ""}
      </span>
      {selected && !selected.is_dir && (
        <button
          type="button"
          onClick={() => onPlay(selected.path)}
          style={{ height: 26, padding: "0 14px", borderRadius: "var(--r-pill)", border: "none", background: "var(--accent-primary)", color: "var(--bg-base)", fontSize: 12, fontWeight: 700, cursor: "pointer" }}
        >
          ▶ REPRODUCIR
        </button>
      )}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
      {children}
    </div>
  );
}

const navBtnStyle = {
  width: 28,
  height: 28,
  borderRadius: "var(--r-xs)",
  border: "none",
  background: "rgba(255,255,255,0.04)",
  color: "var(--text-muted)",
  fontSize: 16,
  cursor: "pointer",
} as const;
