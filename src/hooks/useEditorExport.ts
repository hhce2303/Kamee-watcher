import { useCallback, useState } from "react";
import { exportTimeline } from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";

type ExportState = "idle" | "exporting" | "done" | "error";

interface UseEditorExport {
  state: ExportState;
  progress: number;
  outputPath: string | null;
  error: string | null;
  start: (outputPath: string) => Promise<void>;
}

/** Reel export — progress reported via export_started/progress/finished/failed. */
export function useEditorExport(): UseEditorExport {
  const [state, setState] = useState<ExportState>("idle");
  const [progress, setProgress] = useState(0);
  const [outputPath, setOutputPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useBackendEvent("export_started", () => {
    setState("exporting");
    setProgress(0);
    setError(null);
  });
  useBackendEvent("export_progress", (ev) => setProgress(ev.fraction));
  useBackendEvent("export_finished", (ev) => {
    setState("done");
    setOutputPath(ev.output_path);
  });
  useBackendEvent("export_failed", (ev) => {
    setState("error");
    setError(ev.message);
  });

  const start = useCallback(async (path: string) => {
    setOutputPath(null);
    await exportTimeline(path);
  }, []);

  return { state, progress, outputPath, error, start };
}
