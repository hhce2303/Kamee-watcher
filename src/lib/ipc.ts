import { invoke } from "@tauri-apps/api/core";
import type {
  AnalyticEventDTO,
  BrowseListing,
  ClipDTO,
  ClipEntryDTO,
  ClipInfoDTO,
  ClipRequest,
  CountByClass,
  DwellRecord,
  MediaRoots,
  MonitorDTO,
  OperatorInfo,
  PreviewServerInfo,
  RecordingState,
  SettingsSnapshot,
  ShareResultDTO,
  StorageInfo,
} from "../types/dto";

/**
 * Typed IPC command client — the single Tauri-invoke crossing point of the
 * frontend (hexagonal boundary). One function per backend command, mirroring
 * project/app/adapters/ipc/router.py verbatim (names, payloads, returns).
 *
 * Import rules: `src/hooks/` and stores consume this module; components never
 * import it directly (they go through domain hooks).
 */

export async function ipcSend<T = unknown>(
  cmd: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  return invoke<T>("ipc_send", { cmd, payload });
}

export function ipcConnected(): Promise<boolean> {
  return invoke<boolean>("ipc_connected");
}

// ── Loaded-clip / add-files report shapes (dataclasses in core/api) ──

export interface LoadedClip {
  path: string;
  info: ClipInfoDTO | null;
  ok: boolean;
}

export interface AddFilesReport {
  first_index: number;
  requested: number;
  added: number;
  skipped: string[];
}

// ── Recording ────────────────────────────────────────────────────────

export const getRecordingState = () => ipcSend<RecordingState>("get_recording_state");
export const getMonitors = () => ipcSend<MonitorDTO[]>("get_monitors");
export const getPreviewServerInfo = () =>
  ipcSend<PreviewServerInfo | null>("get_preview_server_info");
export const triggerEvent = () => ipcSend<{ accepted: boolean }>("trigger_event");
export const startRecording = () => ipcSend<RecordingState>("start_recording");
export const stopRecording = () => ipcSend<RecordingState>("stop_recording");
export const toggleMonitor = (fingerprint: string) =>
  ipcSend<MonitorDTO[]>("toggle_monitor", { fingerprint });

// ── Settings ─────────────────────────────────────────────────────────

export const getSettings = () => ipcSend<SettingsSnapshot>("get_settings");
export const getMediaRoots = () => ipcSend<MediaRoots>("get_media_roots");
export const setClipsDir = (path: string) => ipcSend<null>("set_clips_dir", { path });
export const setDriverIndex = (index: number) =>
  ipcSend<null>("set_driver_index", { index });
export const setCodec = (codec: string) => ipcSend<null>("set_codec", { codec });
export const setAutorecord = (enabled: boolean) =>
  ipcSend<null>("set_autorecord", { enabled });
export const setAutostart = (enabled: boolean) =>
  ipcSend<null>("set_autostart", { enabled });
export const applyEncoderNow = () => ipcSend<null>("apply_encoder_now");
export const setRole = (role: string) =>
  ipcSend<{ applied: boolean }>("set_role", { role });
export const unlockIt = (pin: string) => ipcSend<{ ok: boolean }>("unlock_it", { pin });

// ── Editor ───────────────────────────────────────────────────────────

export const addClip = (path: string, durationS: number) =>
  ipcSend<null>("add_clip", { path, duration_s: durationS });
export const addClipTrimmed = (
  path: string,
  durationS: number,
  inFrac: number,
  outFrac: number,
) =>
  ipcSend<null>("add_clip_trimmed", {
    path,
    duration_s: durationS,
    in_frac: inFrac,
    out_frac: outFrac,
  });
export const addFilesFromUrls = (urls: string[]) =>
  ipcSend<AddFilesReport>("add_files_from_urls", { urls });
export const removeClip = (index: number) => ipcSend<null>("remove_clip", { index });
export const moveClip = (src: number, dst: number) =>
  ipcSend<null>("move_clip", { src, dst });
export const setTrim = (index: number, inPointS: number, outPointS: number) =>
  ipcSend<null>("set_trim", { index, in_point_s: inPointS, out_point_s: outPointS });
export const clearTimeline = () => ipcSend<null>("clear_timeline");
export const exportTimeline = (outputPath: string) =>
  ipcSend<null>("export_timeline", { output_path: outputPath });
export const editorClipCount = () => ipcSend<{ count: number }>("editor_clip_count");
export const getTimeline = () => ipcSend<ClipEntryDTO[]>("get_timeline");

// ── Clips / browsing ─────────────────────────────────────────────────

export const listClips = () => ipcSend<ClipDTO[]>("list_clips");
export const loadClip = (path: string) => ipcSend<LoadedClip>("load_clip", { path });
export const listDirectory = (path: string) =>
  ipcSend<BrowseListing>("list_directory", { path });
export const transcodeClip = (path: string) => ipcSend<null>("transcode_clip", { path });
export const cancelTranscode = (path: string) => ipcSend<null>("cancel_transcode", { path });

// ── Requests (Supervisor ↔ IT) ───────────────────────────────────────

export const listStorages = () => ipcSend<StorageInfo[]>("list_storages");
export const listOperators = (storagePath: string) =>
  ipcSend<OperatorInfo[]>("list_operators", { storage_path: storagePath });
export const listAllOperators = () => ipcSend<OperatorInfo[]>("list_all_operators");
export const sendClipRequest = (requestJson: string) =>
  ipcSend<{ ok: boolean }>("send_clip_request", { request_json: requestJson });
export const inboxRequests = () => ipcSend<ClipRequest[]>("inbox_requests");
export const myRequests = () => ipcSend<ClipRequest[]>("my_requests");
export const updateRequestStatus = (requestId: string, status: string) =>
  ipcSend<null>("update_request_status", { request_id: requestId, status });

// ── Delivery (OneDrive) ──────────────────────────────────────────────

export const computeFolderPath = () =>
  ipcSend<{ path: string }>("compute_folder_path");
export const ensureFolderAndLink = (folderPath = "") =>
  ipcSend<ShareResultDTO>("ensure_folder_and_link", { folder_path: folderPath });
export const resetOnedrive = () => ipcSend<null>("reset_onedrive");
export const saveReelPrivately = (folderPath = "") =>
  ipcSend<null>("save_reel_privately", { folder_path: folderPath });

// ── Analytics (F5) ───────────────────────────────────────────────────

export const analyticsCounts = (since: string, until: string, monitorIndex?: number) =>
  ipcSend<CountByClass[]>("analytics_counts", {
    since,
    until,
    monitor_index: monitorIndex ?? null,
  });
export const analyticsDwell = (since: string, until: string, monitorIndex?: number) =>
  ipcSend<DwellRecord[]>("analytics_dwell", {
    since,
    until,
    monitor_index: monitorIndex ?? null,
  });
export const analyticsZoneEvents = (zoneName: string, since: string, until: string) =>
  ipcSend<AnalyticEventDTO[]>("analytics_zone_events", {
    zone_name: zoneName,
    since,
    until,
  });
