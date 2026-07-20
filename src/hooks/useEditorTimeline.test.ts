import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useEditorTimeline } from "./useEditorTimeline";
import { emitFake, invoke } from "../test/tauriMocks";

describe("useEditorTimeline", () => {
  it("loads the timeline on mount via get_timeline", async () => {
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "get_timeline") {
        return [{ source_path: "/a.mp4", source_duration_s: 10, in_point_s: 0, out_point_s: 10 }];
      }
      return undefined;
    });

    const { result } = renderHook(() => useEditorTimeline());
    await waitFor(() => expect(result.current.entries).toHaveLength(1));
    expect(result.current.totalDuration).toBe(10);
  });

  it("refreshes when a timeline_changed event arrives", async () => {
    let call = 0;
    invoke.mockImplementation(async (_cmd: string, args: unknown) => {
      const { cmd } = args as { cmd: string };
      if (cmd === "get_timeline") {
        call += 1;
        return call === 1
          ? []
          : [{ source_path: "/b.mp4", source_duration_s: 5, in_point_s: 1, out_point_s: 4 }];
      }
      return undefined;
    });

    const { result } = renderHook(() => useEditorTimeline());
    await waitFor(() => expect(result.current.entries).toHaveLength(0));

    emitFake("timeline_changed", { event: "timeline_changed" });

    await waitFor(() => expect(result.current.entries).toHaveLength(1));
    expect(result.current.totalDuration).toBe(3);
  });
});
