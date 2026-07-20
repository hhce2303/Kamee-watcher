import { useEffect, useState } from "react";
import { listStorages } from "../lib/ipc";
import type { StorageInfo } from "../types/dto";

/** Canonical storage list for the Supervisor roster filter — includes storages with zero operators. */
export function useStorages(): StorageInfo[] {
  const [storages, setStorages] = useState<StorageInfo[]>([]);

  useEffect(() => {
    listStorages()
      .then(setStorages)
      .catch((e) => console.error("useStorages: list_storages failed", e));
  }, []);

  return storages;
}
