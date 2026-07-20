import { useEffect, useState } from "react";
import { getMediaRoots } from "../lib/ipc";
import type { MediaRoots } from "../types/dto";

interface UseMediaRoots {
  roots: MediaRoots | null;
  error: string | null;
}

/** Filesystem/NAS roots the media protocol allowlists — same source as Rust's own fetch. */
export function useMediaRoots(): UseMediaRoots {
  const [roots, setRoots] = useState<MediaRoots | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMediaRoots()
      .then(setRoots)
      .catch((e) => {
        console.error("useMediaRoots: get_media_roots failed", e);
        setError(String(e));
      });
  }, []);

  return { roots, error };
}
