import { useCallback, useEffect, useState } from "react";
import {
  addClip,
  addFilesFromUrls,
  clearTimeline,
  getTimeline,
  moveClip,
  removeClip,
  setTrim,
} from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";
import type { ClipEntryDTO } from "../types/dto";

interface UseEditorTimeline {
  entries: ClipEntryDTO[];
  totalDuration: number;
  actions: {
    addClip: (path: string, durationS: number) => Promise<void>;
    addFiles: (paths: string[]) => Promise<void>;
    remove: (index: number) => Promise<void>;
    move: (src: number, dst: number) => Promise<void>;
    trim: (index: number, inPointS: number, outPointS: number) => Promise<void>;
    clear: () => Promise<void>;
  };
}

/** Evidence-reel timeline — the backend has no other way to read the clip list. */
export function useEditorTimeline(): UseEditorTimeline {
  const [entries, setEntries] = useState<ClipEntryDTO[]>([]);

  const refresh = useCallback(() => {
    void getTimeline().then(setEntries);
  }, []);

  useEffect(refresh, [refresh]);
  useBackendEvent("timeline_changed", refresh);

  const totalDuration = entries.reduce((sum, e) => sum + (e.out_point_s - e.in_point_s), 0);

  return {
    entries,
    totalDuration,
    actions: {
      addClip: async (path, durationS) => {
        await addClip(path, durationS);
      },
      addFiles: async (paths) => {
        await addFilesFromUrls(paths);
      },
      remove: async (index) => {
        await removeClip(index);
      },
      move: async (src, dst) => {
        await moveClip(src, dst);
      },
      trim: async (index, inPointS, outPointS) => {
        await setTrim(index, inPointS, outPointS);
      },
      clear: async () => {
        await clearTimeline();
      },
    },
  };
}
