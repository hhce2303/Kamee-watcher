import { useEffect } from "react";
import { listen } from "@tauri-apps/api/event";

/**
 * Subscribe to a Tauri event for the lifetime of the component.
 *
 * Events come from two sources:
 *   1. The Rust IPC reader task (pipe events forwarded as Tauri emits).
 *   2. Native Tauri app events (ipc_connected / ipc_disconnected).
 *
 * The handler is called with the event payload (already unwrapped from the
 * Tauri Event<T> wrapper).
 */
export function useTauriEvent<T>(
  event: string,
  handler: (payload: T) => void,
): void {
  useEffect(() => {
    const unlisten = listen<T>(event, (e) => handler(e.payload));
    return () => {
      unlisten.then((fn) => fn());
    };
  }, [event, handler]);
}
