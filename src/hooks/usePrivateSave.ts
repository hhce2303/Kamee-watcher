import { useCallback, useState } from "react";
import { saveReelPrivately } from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";

type SaveState = "idle" | "working" | "saved" | "error";

interface UsePrivateSave {
  state: SaveState;
  folder: string;
  outputPath: string;
  progress: number;
  error: string;
  save: () => Promise<void>;
  reset: () => void;
}

/**
 * Private OneDrive save (IT role) — export + deliver as one action, never a
 * share link. Reuses the existing `export_progress` channel for progress:
 * safe because the backend's mutual-exclusion guard (DeliveryApi.save_reel_privately)
 * guarantees no other export can be running while state === "working".
 */
export function usePrivateSave(): UsePrivateSave {
  const [state, setState] = useState<SaveState>("idle");
  const [folder, setFolder] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  useBackendEvent("onedrive_save_started", () => {
    setState("working");
    setProgress(0);
    setError("");
  });
  useBackendEvent("export_progress", (ev) => {
    setProgress(ev.fraction);
  });
  useBackendEvent("onedrive_saved", (ev) => {
    setState("saved");
    setFolder(ev.folder_path);
    setOutputPath(ev.output_path);
  });
  useBackendEvent("onedrive_save_failed", (ev) => {
    setState("error");
    setError(ev.message);
  });

  const save = useCallback(async () => {
    setState("working");
    setError("");
    await saveReelPrivately();
  }, []);

  const reset = useCallback(() => {
    setState("idle");
    setFolder("");
    setOutputPath("");
    setProgress(0);
    setError("");
  }, []);

  return { state, folder, outputPath, progress, error, save, reset };
}
