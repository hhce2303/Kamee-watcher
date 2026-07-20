import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useRecording } from "./useRecording";
import { emitFake, invoke } from "../test/tauriMocks";

describe("useRecording", () => {
  it("loads the initial snapshot via get_recording_state / get_monitors", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "get_recording_state") {
        return { is_recording: false, record_seconds: 0, event_count: 0 };
      }
      if (cmd === "get_monitors") return [];
      return undefined;
    });

    const { result } = renderHook(() => useRecording());

    await waitFor(() => expect(result.current.state).not.toBeNull());
    expect(result.current.state?.is_recording).toBe(false);
  });

  it("updates state from a recording_state_changed push event", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "get_recording_state") {
        return { is_recording: false, record_seconds: 0, event_count: 0 };
      }
      if (cmd === "get_monitors") return [];
      return undefined;
    });

    const { result } = renderHook(() => useRecording());
    await waitFor(() => expect(result.current.state).not.toBeNull());

    act(() => {
      emitFake("recording_state_changed", {
        event: "recording_state_changed",
        state: { is_recording: true, record_seconds: 5, event_count: 2 },
      });
    });

    expect(result.current.state?.is_recording).toBe(true);
    expect(result.current.state?.record_seconds).toBe(5);
  });

  it("surfaces recording_failed events as an error", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "get_recording_state") {
        return { is_recording: false, record_seconds: 0, event_count: 0 };
      }
      if (cmd === "get_monitors") return [];
      return undefined;
    });

    const { result } = renderHook(() => useRecording());
    await waitFor(() => expect(result.current.state).not.toBeNull());

    act(() => {
      emitFake("recording_failed", { event: "recording_failed", message: "ffmpeg crashed" });
    });

    expect(result.current.error).toBe("ffmpeg crashed");
  });
});
