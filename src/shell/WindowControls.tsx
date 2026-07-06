import { getCurrentWindow } from "@tauri-apps/api/window";
import type { CSSProperties } from "react";
import type { RolePolicy } from "../lib/policy";

interface WindowControlsProps {
  policy: RolePolicy;
}

/**
 * Minimize/close controls, gated by role policy.
 *
 * The operator's "indestructible window" is enforced in Rust (src-tauri
 * `on_window_event` CloseRequested → hide-to-tray), so hiding the close
 * button here is a UX nicety, not the security boundary.
 *
 * `getCurrentWindow()` is called lazily inside the handlers (not at module
 * scope) — it touches `window.__TAURI_INTERNALS__`, which does not exist
 * outside a real Tauri webview (e.g. in vitest/jsdom).
 */
export default function WindowControls({ policy }: WindowControlsProps) {
  return (
    <div style={{ display: "flex", gap: "var(--sp-2)" }}>
      {policy.canMinimizeWindow && (
        <button
          type="button"
          aria-label="Minimizar"
          onClick={() => void getCurrentWindow().minimize()}
          style={ctrlStyle}
        >
          –
        </button>
      )}
      {policy.canCloseWindow && (
        <button
          type="button"
          aria-label="Cerrar"
          onClick={() => void getCurrentWindow().close()}
          style={ctrlStyle}
        >
          ×
        </button>
      )}
    </div>
  );
}

const ctrlStyle: CSSProperties = {
  width: 28,
  height: 24,
  border: "1px solid var(--border-base)",
  background: "var(--bg-base)",
  color: "var(--text-muted)",
  borderRadius: "var(--r-xs)",
  cursor: "pointer",
  fontSize: 14,
  lineHeight: 1,
};
