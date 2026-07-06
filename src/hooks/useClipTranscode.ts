import { useCallback, useState } from "react";
import { transcodeClip } from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";

interface UseClipTranscode {
  transcoding: boolean;
  progress: number;
  outputPath: string | null;
  error: string | null;
  start: (path: string) => void;
}

/** Drives the HEVC→H.264 on-demand transcode (player fallback) for one path at a time. */
export function useClipTranscode(): UseClipTranscode {
  const [activePath, setActivePath] = useState<string | null>(null);
  const [transcoding, setTranscoding] = useState(false);
  const [progress, setProgress] = useState(0);
  const [outputPath, setOutputPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useBackendEvent("transcode_started", (ev) => {
    if (ev.path !== activePath) return;
    setTranscoding(true);
    setProgress(0);
    setError(null);
  });
  useBackendEvent("transcode_progress", (ev) => {
    if (ev.path !== activePath) return;
    setProgress(ev.fraction);
  });
  useBackendEvent("transcode_finished", (ev) => {
    if (ev.path !== activePath) return;
    setTranscoding(false);
    setOutputPath(ev.output_path);
  });
  useBackendEvent("transcode_failed", (ev) => {
    if (ev.path !== activePath) return;
    setTranscoding(false);
    setError(ev.message);
  });

  const start = useCallback((path: string) => {
    setActivePath(path);
    setOutputPath(null);
    setError(null);
    void transcodeClip(path).catch((e) => setError(String(e)));
  }, []);

  return { transcoding, progress, outputPath, error, start };
}
