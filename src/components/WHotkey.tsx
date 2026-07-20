import "./primitives.css";

interface WHotkeyProps {
  keys: string[];
}

export default function WHotkey({ keys }: WHotkeyProps) {
  return (
    <span className="w-hotkey">
      {keys.map((key, i) => (
        <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <span className="w-hotkey__key">{key}</span>
          {i < keys.length - 1 && <span className="w-hotkey__plus">+</span>}
        </span>
      ))}
    </span>
  );
}
