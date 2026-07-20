import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useClipTranscode } from "./useClipTranscode";
import { emitFake, invoke } from "../test/tauriMocks";

describe("useClipTranscode", () => {
  it("start() calls transcode_clip and reflects push-event progress through to finished", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "transcode_clip") return null;
      return undefined;
    });

    const { result } = renderHook(() => useClipTranscode());

    act(() => {
      result.current.start("/a.mkv");
    });

    act(() => {
      emitFake("transcode_started", { event: "transcode_started", path: "/a.mkv" });
    });
    await waitFor(() => expect(result.current.transcoding).toBe(true));

    act(() => {
      emitFake("transcode_progress", { event: "transcode_progress", path: "/a.mkv", fraction: 0.5 });
    });
    await waitFor(() => expect(result.current.progress).toBe(0.5));

    act(() => {
      emitFake("transcode_finished", { event: "transcode_finished", path: "/a.mkv", output_path: "/a_converted.mp4" });
    });
    await waitFor(() => expect(result.current.transcoding).toBe(false));
    expect(result.current.outputPath).toBe("/a_converted.mp4");
  });

  it("ignores push events for a different path than the one just started", async () => {
    invoke.mockImplementation(async () => null);
    const { result } = renderHook(() => useClipTranscode());

    act(() => {
      result.current.start("/a.mkv");
    });
    act(() => {
      emitFake("transcode_progress", { event: "transcode_progress", path: "/unrelated.mkv", fraction: 0.9 });
    });

    expect(result.current.progress).toBe(0);
  });

  it("cancel() calls cancel_transcode and the resulting transcode_failed event surfaces as the normal error state", async () => {
    const calls: string[] = [];
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      calls.push(cmd);
      return null;
    });

    const { result } = renderHook(() => useClipTranscode());
    act(() => {
      result.current.start("/a.mkv");
    });
    act(() => {
      emitFake("transcode_started", { event: "transcode_started", path: "/a.mkv" });
    });
    await waitFor(() => expect(result.current.transcoding).toBe(true));

    act(() => {
      result.current.cancel("/a.mkv");
    });
    await waitFor(() => expect(calls).toContain("cancel_transcode"));

    act(() => {
      emitFake("transcode_failed", { event: "transcode_failed", path: "/a.mkv", message: "Conversión cancelada por el usuario." });
    });
    await waitFor(() => expect(result.current.transcoding).toBe(false));
    expect(result.current.error).toContain("cancelada");
  });
});
