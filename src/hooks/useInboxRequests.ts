import { useCallback, useEffect, useState } from "react";
import { inboxRequests, updateRequestStatus } from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";
import type { ClipRequest } from "../types/dto";

interface UseInboxRequests {
  requests: ClipRequest[];
  setStatus: (requestId: string, status: string) => Promise<void>;
}

/** IT-side inbox: requests received from Supervisors, with status transitions. */
export function useInboxRequests(): UseInboxRequests {
  const [requests, setRequests] = useState<ClipRequest[]>([]);

  const refresh = useCallback(() => {
    void inboxRequests().then(setRequests);
  }, []);

  useEffect(refresh, [refresh]);
  useBackendEvent("request_received", refresh);
  useBackendEvent("request_status_changed", refresh);

  const setStatus = useCallback(
    async (requestId: string, status: string) => {
      await updateRequestStatus(requestId, status);
      refresh();
    },
    [refresh],
  );

  return { requests, setStatus };
}
