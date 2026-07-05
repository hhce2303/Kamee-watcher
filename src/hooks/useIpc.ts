import { invoke } from "@tauri-apps/api/core";

/**
 * Thin wrapper over the `ipc_send` Tauri command.
 *
 * The Rust command proxies the call through the named-pipe to the Python
 * backend (ADR-0011 — authenticated local channel).  The backend returns a
 * response envelope; on success the caller receives the `result` value
 * already unwrapped, on error a string is thrown.
 */
export function useIpc() {
  async function send<T = unknown>(
    cmd: string,
    payload: Record<string, unknown> = {},
  ): Promise<T> {
    return invoke<T>("ipc_send", { cmd, payload });
  }

  return { send };
}
