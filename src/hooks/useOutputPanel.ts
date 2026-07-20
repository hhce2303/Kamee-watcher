import { useCallback, useState } from "react";
import { computeFolderPath, ensureFolderAndLink, resetOnedrive } from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";

type SaveState = "idle" | "working" | "linked" | "error";

interface UseOutputPanel {
  state: SaveState;
  folder: string;
  link: string;
  error: string;
  save: () => Promise<void>;
  reset: () => Promise<void>;
}

/** OneDrive delivery (folder + share link) — port of the OutputPanel.qml flow. */
export function useOutputPanel(): UseOutputPanel {
  const [state, setState] = useState<SaveState>("idle");
  const [folder, setFolder] = useState("");
  const [link, setLink] = useState("");
  const [error, setError] = useState("");

  useBackendEvent("onedrive_changed", (ev) => {
    setState(ev.state as SaveState);
    setFolder(ev.folder);
    setLink(ev.link);
  });
  useBackendEvent("onedrive_failed", (ev) => {
    setState("error");
    setError(ev.message);
  });

  const save = useCallback(async () => {
    setState("working");
    setError("");
    try {
      const { path } = await computeFolderPath();
      const result = await ensureFolderAndLink(path);
      setState("linked");
      setFolder(result.folder_path);
      setLink(result.share_link);
    } catch (e) {
      setState("error");
      setError(String(e));
    }
  }, []);

  const reset = useCallback(async () => {
    await resetOnedrive();
    setState("idle");
    setFolder("");
    setLink("");
    setError("");
  }, []);

  return { state, folder, link, error, save, reset };
}
