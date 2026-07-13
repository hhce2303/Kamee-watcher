import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { invoke } from "@tauri-apps/api/core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClipBrowser from "./ClipBrowser";
import type { BrowseEntry, BrowseListing, MediaRoots } from "../../types/dto";

const mockedInvoke = invoke as unknown as ReturnType<typeof vi.fn>;

const ROOTS: MediaRoots = {
  segments_dir: "C:/WatcherData/segments",
  clips_dir: "C:/WatcherData/clips",
  storage_roots: ["\\\\SIG-SLC-Storage"],
};

function entry(overrides: Partial<BrowseEntry> = {}): BrowseEntry {
  return {
    name: "clip.mp4",
    path: "LOCAL_CLIPS/clip.mp4",
    is_dir: false,
    modified: "2026-07-01",
    size: "12 MB",
    ext: "mp4",
    ...overrides,
  };
}

/** Route ipc_send({cmd, payload}) calls to per-command fake responses. */
function stubIpc(responses: Record<string, unknown>) {
  mockedInvoke.mockImplementation(async (command: string, args?: Record<string, unknown>) => {
    if (command === "ipc_send") {
      const cmd = args?.cmd as string;
      if (cmd in responses) return responses[cmd];
      return undefined;
    }
    return undefined;
  });
}

describe("ClipBrowser", () => {
  beforeEach(() => {
    mockedInvoke.mockReset();
  });

  it("prompts to pick a location before anything is loaded", () => {
    stubIpc({ get_media_roots: ROOTS });
    render(<ClipBrowser onPlay={() => {}} />);
    expect(screen.getByText("Selecciona una ubicación")).toBeInTheDocument();
  });

  it("loads and lists entries after picking a location", async () => {
    const listing: BrowseListing = { entries: [entry({ name: "a.mp4" }), entry({ name: "b.mp4" })], failed: false };
    stubIpc({ get_media_roots: ROOTS, list_directory: listing });
    render(<ClipBrowser onPlay={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /Clips combinados/ }));

    await waitFor(() => expect(screen.getByText("a.mp4")).toBeInTheDocument());
    expect(screen.getByText("b.mp4")).toBeInTheDocument();
  });

  it("navigates into a folder on double-click and updates the breadcrumb", async () => {
    const rootListing: BrowseListing = { entries: [entry({ name: "sub", is_dir: true, path: "LOCAL_CLIPS/sub" })], failed: false };
    const subListing: BrowseListing = { entries: [entry({ name: "inner.mp4" })], failed: false };
    mockedInvoke.mockImplementation(async (command: string, args?: Record<string, unknown>) => {
      if (command !== "ipc_send") return undefined;
      const cmd = args?.cmd as string;
      if (cmd === "get_media_roots") return ROOTS;
      if (cmd === "list_directory") {
        const path = (args?.payload as { path: string }).path;
        return path === "LOCAL_CLIPS/sub" ? subListing : rootListing;
      }
      return undefined;
    });
    render(<ClipBrowser onPlay={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /Clips combinados/ }));
    await waitFor(() => expect(screen.getByText("sub")).toBeInTheDocument());

    await userEvent.dblClick(screen.getByText("sub"));

    await waitFor(() => expect(screen.getByText("inner.mp4")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "sub" })).toBeInTheDocument(); // breadcrumb crumb
  });

  it("selects a file on click and plays it from the status bar", async () => {
    const listing: BrowseListing = { entries: [entry({ name: "clip.mp4", path: "LOCAL_CLIPS/clip.mp4" })], failed: false };
    stubIpc({ get_media_roots: ROOTS, list_directory: listing });
    const onPlay = vi.fn();
    render(<ClipBrowser onPlay={onPlay} />);

    await userEvent.click(screen.getByRole("button", { name: /Clips combinados/ }));
    await waitFor(() => expect(screen.getByText("clip.mp4")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("option", { name: /clip.mp4/ }));
    await userEvent.click(screen.getByRole("button", { name: "▶ REPRODUCIR" }));

    expect(onPlay).toHaveBeenCalledWith("LOCAL_CLIPS/clip.mp4");
  });

  it("shows a failed state distinctly from an empty folder", async () => {
    stubIpc({ get_media_roots: ROOTS, list_directory: { entries: [], failed: true } });
    render(<ClipBrowser onPlay={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /Clips combinados/ }));

    await waitFor(() => expect(screen.getByText(/Sin conexión/)).toBeInTheDocument());
  });
});
