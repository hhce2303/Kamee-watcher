import { useCallback, useState } from "react";
import { listDirectory } from "../lib/ipc";
import type { BrowseEntry } from "../types/dto";

interface Crumb {
  label: string;
  path: string;
}

interface UseClipBrowser {
  navStack: Crumb[];
  items: BrowseEntry[];
  selected: BrowseEntry | null;
  loading: boolean;
  failed: boolean;
  select: (entry: BrowseEntry | null) => void;
  openItem: (entry: BrowseEntry) => void;
  openLocation: (label: string, path: string) => void;
  goToCrumb: (index: number) => void;
  goBack: () => void;
  reload: () => void;
}

/** Navigation/data logic for ClipBrowser — no JSX, per the hexagonal boundary. */
export function useClipBrowser(): UseClipBrowser {
  const [navStack, setNavStack] = useState<Crumb[]>([]);
  const [items, setItems] = useState<BrowseEntry[]>([]);
  const [selected, setSelected] = useState<BrowseEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async (path: string) => {
    setLoading(true);
    setFailed(false);
    try {
      const listing = await listDirectory(path);
      setItems(listing.entries);
      setFailed(listing.failed);
    } catch {
      setItems([]);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const openLocation = useCallback(
    (label: string, path: string) => {
      setNavStack([{ label, path }]);
      setSelected(null);
      void load(path);
    },
    [load],
  );

  const openItem = useCallback(
    (entry: BrowseEntry) => {
      if (!entry.is_dir) {
        setSelected(entry);
        return;
      }
      setNavStack((prev) => [...prev, { label: entry.name, path: entry.path }]);
      setSelected(null);
      void load(entry.path);
    },
    [load],
  );

  const goToCrumb = useCallback(
    (index: number) => {
      setNavStack((prev) => {
        const next = prev.slice(0, index + 1);
        setSelected(null);
        void load(next[next.length - 1].path);
        return next;
      });
    },
    [load],
  );

  const goBack = useCallback(() => {
    setNavStack((prev) => {
      if (prev.length <= 1) {
        setItems([]);
        setSelected(null);
        return [];
      }
      const next = prev.slice(0, -1);
      setSelected(null);
      void load(next[next.length - 1].path);
      return next;
    });
  }, [load]);

  const reload = useCallback(() => {
    if (navStack.length > 0) void load(navStack[navStack.length - 1].path);
  }, [navStack, load]);

  return {
    navStack,
    items,
    selected,
    loading,
    failed,
    select: setSelected,
    openItem,
    openLocation,
    goToCrumb,
    goBack,
    reload,
  };
}
