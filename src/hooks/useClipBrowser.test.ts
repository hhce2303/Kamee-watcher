import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useClipBrowser } from "./useClipBrowser";
import { invoke } from "../test/tauriMocks";

function mockListing(byPath: Record<string, { entries: unknown[]; failed?: boolean }>) {
  invoke.mockImplementation(async (_cmd: string, args: unknown) => {
    const { cmd, payload } = args as { cmd: string; payload: { path: string } };
    if (cmd === "list_directory") {
      const hit = byPath[payload.path];
      return hit ? { entries: hit.entries, failed: hit.failed ?? false } : { entries: [], failed: true };
    }
    return undefined;
  });
}

describe("useClipBrowser", () => {
  it("openLocation loads the root directory and sets a single breadcrumb", async () => {
    mockListing({ LOCAL_CLIPS: { entries: [{ name: "a.mp4", path: "LOCAL_CLIPS/a.mp4", is_dir: false }] } });
    const { result } = renderHook(() => useClipBrowser());

    act(() => result.current.openLocation("Clips combinados", "LOCAL_CLIPS"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    expect(result.current.navStack).toEqual([{ label: "Clips combinados", path: "LOCAL_CLIPS" }]);
    expect(result.current.failed).toBe(false);
  });

  it("openItem on a directory pushes a breadcrumb and loads its contents", async () => {
    mockListing({
      LOCAL_CLIPS: { entries: [{ name: "sub", path: "LOCAL_CLIPS/sub", is_dir: true }] },
      "LOCAL_CLIPS/sub": { entries: [{ name: "b.mp4", path: "LOCAL_CLIPS/sub/b.mp4", is_dir: false }] },
    });
    const { result } = renderHook(() => useClipBrowser());
    act(() => result.current.openLocation("Clips combinados", "LOCAL_CLIPS"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    act(() => result.current.openItem(result.current.items[0]));
    await waitFor(() => expect(result.current.navStack).toHaveLength(2));
    expect(result.current.items[0].name).toBe("b.mp4");
  });

  it("openItem on a file selects it instead of navigating", async () => {
    mockListing({ LOCAL_CLIPS: { entries: [{ name: "a.mp4", path: "LOCAL_CLIPS/a.mp4", is_dir: false }] } });
    const { result } = renderHook(() => useClipBrowser());
    act(() => result.current.openLocation("Clips combinados", "LOCAL_CLIPS"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));

    act(() => result.current.openItem(result.current.items[0]));
    expect(result.current.selected?.name).toBe("a.mp4");
    expect(result.current.navStack).toHaveLength(1); // did not navigate
  });

  it("goBack pops the breadcrumb and reloads the parent", async () => {
    mockListing({
      LOCAL_CLIPS: { entries: [{ name: "sub", path: "LOCAL_CLIPS/sub", is_dir: true }] },
      "LOCAL_CLIPS/sub": { entries: [] },
    });
    const { result } = renderHook(() => useClipBrowser());
    act(() => result.current.openLocation("Clips combinados", "LOCAL_CLIPS"));
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    act(() => result.current.openItem(result.current.items[0]));
    await waitFor(() => expect(result.current.navStack).toHaveLength(2));

    act(() => result.current.goBack());
    await waitFor(() => expect(result.current.navStack).toHaveLength(1));
    expect(result.current.items).toHaveLength(1);
  });

  it("a failed listing with no entries sets failed=true", async () => {
    mockListing({ LOCAL_CLIPS: { entries: [], failed: true } });
    const { result } = renderHook(() => useClipBrowser());
    act(() => result.current.openLocation("Clips combinados", "LOCAL_CLIPS"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.failed).toBe(true);
  });
});
