import { ipcSend } from "../lib/ipc";

/**
 * Thin wrapper over the `ipc_send` Tauri command.
 *
 * Prefer the typed per-command functions in `src/lib/ipc.ts` (consumed by
 * domain hooks); this generic hook remains for ad-hoc/legacy call sites.
 */
export function useIpc() {
  return { send: ipcSend };
}
