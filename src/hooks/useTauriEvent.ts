import { useEffect, useRef } from "react";
import { listen } from "@tauri-apps/api/event";

/**
 * Subscribe to a native Tauri app event (ipc_connected / ipc_disconnected)
 * for the lifetime of the component.
 *
 * For backend pipe events use `useBackendEvent` instead — it types the
 * snake_case discriminators and the envelope payload.
 *
 * The handler is kept in a ref so an unstable (inline) handler does not
 * re-subscribe on every render.
 */
export function useTauriEvent<T>(
  event: string,
  handler: (payload: T) => void,
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const unlisten = listen<T>(event, (e) => handlerRef.current(e.payload));
    return () => {
      unlisten.then((fn) => fn());
    };
  }, [event]);
}
