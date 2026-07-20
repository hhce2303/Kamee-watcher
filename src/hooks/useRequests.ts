import { useCallback, useEffect, useState } from "react";
import { listAllOperators, myRequests as fetchMyRequests, sendClipRequest } from "../lib/ipc";
import { useBackendEvent } from "./useBackendEvent";
import type { ClipRequest, OperatorInfo } from "../types/dto";

interface SendRequestInput {
  operator: string;
  storage: string;
  startTime: string;
  endTime: string;
  description: string;
}

interface UseRequests {
  operators: OperatorInfo[];
  myRequests: ClipRequest[];
  sending: boolean;
  send: (input: SendRequestInput) => Promise<boolean>;
}

/** Supervisor-side request workflow — list operators, send + track requests. */
export function useRequests(): UseRequests {
  const [operators, setOperators] = useState<OperatorInfo[]>([]);
  const [requests, setRequests] = useState<ClipRequest[]>([]);
  const [sending, setSending] = useState(false);

  const refreshRequests = useCallback(() => {
    void fetchMyRequests().then(setRequests);
  }, []);

  useEffect(() => {
    void listAllOperators().then(setOperators);
    refreshRequests();
  }, [refreshRequests]);

  useBackendEvent("request_status_changed", refreshRequests);

  const send = useCallback(
    async (input: SendRequestInput) => {
      setSending(true);
      try {
        const requestJson = JSON.stringify({
          operator: input.operator,
          storage: input.storage,
          start_time: input.startTime,
          end_time: input.endTime,
          description: input.description,
        });
        const { ok } = await sendClipRequest(requestJson);
        if (ok) refreshRequests();
        return ok;
      } finally {
        setSending(false);
      }
    },
    [refreshRequests],
  );

  return { operators, myRequests: requests, sending, send };
}
