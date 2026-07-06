import { useEffect, useState } from "react";
import { getMediaRoots } from "../lib/ipc";
import type { MediaRoots } from "../types/dto";

/** Filesystem/NAS roots the media protocol allowlists — same source as Rust's own fetch. */
export function useMediaRoots(): MediaRoots | null {
  const [roots, setRoots] = useState<MediaRoots | null>(null);

  useEffect(() => {
    getMediaRoots()
      .then(setRoots)
      .catch((e) => console.error("useMediaRoots: get_media_roots failed", e));
  }, []);

  return roots;
}
