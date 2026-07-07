import { useState } from "react";

interface PinUnlockPromptProps {
  onUnlock: (pin: string) => Promise<boolean>;
  label?: string;
}

/** PIN entry + "Desbloquear" button — shared by SettingsView's role-change row and the IT ajustes gate. */
export default function PinUnlockPrompt({ onUnlock, label = "PIN IT" }: PinUnlockPromptProps) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleUnlock() {
    const ok = await onUnlock(pin);
    setError(ok ? null : "PIN incorrecto");
    if (ok) setPin("");
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          type="password"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          placeholder={label}
          style={{ width: 100, height: 32, padding: "0 10px", borderRadius: "var(--r-sm)", border: "1px solid var(--border-base)", background: "var(--bg-base)", color: "var(--text-primary)" }}
        />
        <button
          type="button"
          onClick={handleUnlock}
          style={{ height: 32, padding: "0 16px", borderRadius: "var(--r-sm)", border: "none", background: "var(--accent-primary)", color: "var(--bg-base)", fontSize: 13, fontWeight: 700, cursor: "pointer" }}
        >
          Desbloquear
        </button>
      </div>
      {error && <p style={{ color: "var(--accent-record)", fontSize: 12 }}>{error}</p>}
    </div>
  );
}
