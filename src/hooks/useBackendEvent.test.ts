import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useBackendEvent } from "./useBackendEvent";
import { emitFake } from "../test/tauriMocks";

describe("useBackendEvent", () => {
  it("subscribes under the exact snake_case discriminator (regression: M0 transport bug)", () => {
    const handler = vi.fn();
    renderHook(() => useBackendEvent("recording_state_changed", handler));

    // PascalCase must NOT trigger the handler — this is the bug that made
    // push events silently never arrive before the A1 transport fix.
    emitFake("RecordingStateChanged", { event: "RecordingStateChanged" });
    expect(handler).not.toHaveBeenCalled();

    emitFake("recording_state_changed", {
      event: "recording_state_changed",
      state: { is_recording: true, record_seconds: 12, event_count: 1 },
    });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("passes the whole envelope, not an unwrapped DTO (regression: M0 payload-shape bug)", () => {
    const handler = vi.fn();
    renderHook(() => useBackendEvent("monitors_changed", handler));

    const envelope = { event: "monitors_changed" as const, monitors: [] };
    emitFake("monitors_changed", envelope);

    expect(handler).toHaveBeenCalledWith(envelope);
  });

  it("does not re-subscribe when handler identity changes across renders", () => {
    const { rerender } = renderHook(
      ({ handler }: { handler: () => void }) => useBackendEvent("clips_changed", handler),
      { initialProps: { handler: () => {} } },
    );
    const firstHandler = vi.fn();
    const secondHandler = vi.fn();
    rerender({ handler: firstHandler });
    rerender({ handler: secondHandler });

    emitFake("clips_changed", { event: "clips_changed", clips: [] });

    expect(firstHandler).not.toHaveBeenCalled();
    expect(secondHandler).toHaveBeenCalledTimes(1);
  });
});
