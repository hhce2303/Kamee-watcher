import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { CountByClass, DwellRecord } from "../types/dto";

export interface AnalyticsFilters {
  since: string;   // ISO-8601
  until: string;   // ISO-8601
  monitorIndex: number | null;
  zoneName: string;
}

export interface AnalyticEventRaw {
  event_id: string;
  type: string;
  start: string;
  end: string;
  duration_seconds: number;
  monitor_index: number | null;
  track_id: number | null;
  zone: string | null;
  confidence: number | null;
}

export interface AnalyticsData {
  counts: CountByClass[];
  dwell: DwellRecord[];
  zoneEvents: AnalyticEventRaw[];
  loading: boolean;
  error: string | null;
}

const POLL_MS = 10_000;

export function useLiveAnalytics(filters: AnalyticsFilters): AnalyticsData & { refresh: () => void } {
  const [counts, setCounts]         = useState<CountByClass[]>([]);
  const [dwell, setDwell]           = useState<DwellRecord[]>([]);
  const [zoneEvents, setZoneEvents] = useState<AnalyticEventRaw[]>([]);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const base = { since: filters.since, until: filters.until, monitor_index: filters.monitorIndex };
      const [c, d, z] = await Promise.all([
        invoke<CountByClass[]>("analytics_counts", { filter: base }),
        invoke<DwellRecord[]>("analytics_dwell",   { filter: base }),
        filters.zoneName
          ? invoke<AnalyticEventRaw[]>("analytics_zone_events", {
              filter: { zone_name: filters.zoneName, since: filters.since, until: filters.until },
            })
          : Promise.resolve([] as AnalyticEventRaw[]),
      ]);
      setCounts(c);
      setDwell(d);
      setZoneEvents(z);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [filters.since, filters.until, filters.monitorIndex, filters.zoneName]);

  useEffect(() => {
    fetch();
    timerRef.current = setInterval(fetch, POLL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetch]);

  return { counts, dwell, zoneEvents, loading, error, refresh: fetch };
}
