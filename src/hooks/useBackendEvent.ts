import { useEffect, useRef } from "react";
import { listen } from "@tauri-apps/api/event";
import type { BackendEventMap, BackendEventName } from "../types/dto";

/**
 * Subscribe to a backend pipe event for the lifetime of the component.
 *
 * The Rust IPC reader (src-tauri/src/ipc.rs) re-emits every pipe frame under
 * its snake_case discriminator (dto.py) with the WHOLE envelope as payload —
 * the handler receives `{event, ...fields}`, not the bare DTO.
 *
 * The handler is kept in a ref so an unstable (inline) handler does not
 * re-subscribe on every render.
 */
export function useBackendEvent<K extends BackendEventName>(
  event: K,
  handler: (envelope: BackendEventMap[K]) => void,
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const unlisten = listen<BackendEventMap[K]>(event, (e) =>
      handlerRef.current(e.payload),
    );
    return () => {
      unlisten.then((fn) => fn());
    };
  }, [event]);
}
