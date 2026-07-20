import { vi } from "vitest";

/**
 * In-memory fakes for the two Tauri APIs the frontend crosses the hexagonal
 * boundary through: `invoke` (commands) and `listen` (backend pipe events +
 * native app events). Wired globally via vitest.config.ts `setupFiles`.
 */

type Handler = (event: { payload: unknown }) => void;

const listeners = new Map<string, Set<Handler>>();

export const invoke = vi.fn(async (_cmd: string, ..._args: unknown[]): Promise<unknown> => {
  return undefined;
});

export const listen = vi.fn(async (event: string, handler: Handler) => {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event)!.add(handler);
  return () => {
    listeners.get(event)?.delete(handler);
  };
});

/** Simulate a Tauri event (backend pipe frame or native app event) firing. */
export function emitFake(event: string, payload: unknown): void {
  const set = listeners.get(event);
  if (!set) return;
  for (const handler of set) handler({ payload });
}

export function resetTauriMocks(): void {
  listeners.clear();
  invoke.mockReset();
  invoke.mockImplementation(async () => undefined);
  listen.mockClear();
}
