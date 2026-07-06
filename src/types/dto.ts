/**
 * TypeScript mirror of project/app/core/api/dto.py (ADR-0009).
 *
 * Keep in sync with the Python source. These types reflect the JSON that
 * the IPC framing layer (adapters/ipc/protocol.py) serialises over the pipe.
 * Field names are snake_case to match Python model_dump() output verbatim.
 *
 * Event discriminators are snake_case Literal values from dto.py — the Rust
 * shell re-emits each pipe event under its discriminator string with the WHOLE
 * envelope ({event, ...fields}) as the Tauri event payload (src-tauri/src/ipc.rs).
 */

// ── State / response DTOs ────────────────────────────────────────────

export interface MonitorDTO {
  name: string;
  device_name: string;
  resolution: string;
  fingerprint: string;
  index: number;
  x: number;
  y: number;
  is_primary: boolean;
  selected: boolean;
}

export interface RecordingState {
  is_recording: boolean;
  record_seconds: number;
  event_count: number;
}

export interface ClipInfoDTO {
  resolution: string;
  codec: string;
  fps: string;
  bitrate: string;
  duration_seconds: number;
}

export interface ClipDTO {
  clip_name: string;
  path: string;
  size_label: string;
  date_label: string;
  is_event: boolean;
}

export interface ShareResultDTO {
  folder_path: string;
  share_link: string;
}

export interface ClipEntryDTO {
  source_path: string;
  source_duration_s: number;
  in_point_s: number;
  out_point_s: number;
}

export interface SettingsSnapshot {
  role: string;
  clips_dir: string;
  codec: string;
  driver: string;
  autorecord: boolean;
  autostart: boolean;
  it_unlocked: boolean;
}

export interface MediaRoots {
  segments_dir: string;
  clips_dir: string;
  storage_roots: string[];
}

// ── Browsing / requests (dataclasses serialised by router._ser) ─────

export interface BrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
  modified: string;
  size: string;
  ext: string;
}

export interface BrowseListing {
  entries: BrowseEntry[];
  /** True on a real connection/permission failure (vs. empty directory). */
  failed: boolean;
}

export interface StorageInfo {
  name: string;
  path: string;
  operator_count: number;
}

export interface OperatorInfo {
  name: string;
  /** Storage share name only — no navigable path (security contract). */
  storage: string;
}

export interface ClipRequest {
  id: string;
  created_at: string;      // ISO-8601 UTC
  supervisor_host: string;
  operator: string;
  storage: string;
  start_time: string;      // "YYYY-MM-DD HH:MM"
  end_time: string;        // "YYYY-MM-DD HH:MM"
  description: string;
  status: "pending" | "processing" | "done" | "declined";
}

// ── Event DTOs (backend → UI push; payload = whole envelope) ────────

export interface RecordingStateChangedEvent {
  event: "recording_state_changed";
  state: RecordingState;
}

export interface MonitorsChangedEvent {
  event: "monitors_changed";
  monitors: MonitorDTO[];
}

export interface ClipsChangedEvent {
  event: "clips_changed";
  clips: ClipDTO[];
}

export interface RecordingFailedEvent {
  event: "recording_failed";
  message: string;
}

export interface ClipFailedEvent {
  event: "clip_failed";
  message: string;
}

export interface LogMessageEvent {
  event: "log_message";
  message: string;
}

export interface RequestShowWindowEvent {
  event: "request_show_window";
}

export interface TimelineChangedEvent {
  event: "timeline_changed";
}

export interface ExportStartedEvent {
  event: "export_started";
}

export interface ExportProgressEvent {
  event: "export_progress";
  fraction: number;
}

export interface ExportFinishedEvent {
  event: "export_finished";
  output_path: string;
}

export interface ExportFailedEvent {
  event: "export_failed";
  message: string;
}

export interface OneDriveChangedEvent {
  event: "onedrive_changed";
  state: "idle" | "working" | "linked" | "error";
  folder: string;
  link: string;
}

export interface OneDriveFailedEvent {
  event: "onedrive_failed";
  message: string;
}

export interface RequestReceivedEvent {
  event: "request_received";
}

export interface RequestStatusChangedEvent {
  event: "request_status_changed";
  request_id: string;
  status: string;
}

export interface RoleChangedEvent {
  event: "role_changed";
  role: string;
  it_unlocked: boolean;
}

export interface TranscodeStartedEvent {
  event: "transcode_started";
  path: string;
}

export interface TranscodeProgressEvent {
  event: "transcode_progress";
  path: string;
  fraction: number;
}

export interface TranscodeFinishedEvent {
  event: "transcode_finished";
  path: string;
  output_path: string;
}

export interface TranscodeFailedEvent {
  event: "transcode_failed";
  path: string;
  message: string;
}

export interface EncoderRestartStartedEvent {
  event: "encoder_restart_started";
}

export interface EncoderRestartFinishedEvent {
  event: "encoder_restart_finished";
}

export interface EncoderRestartFailedEvent {
  event: "encoder_restart_failed";
  message: string;
}

/** Discriminator → envelope map. Source of truth: dto.py BaseEvent subclasses. */
export interface BackendEventMap {
  recording_state_changed: RecordingStateChangedEvent;
  monitors_changed: MonitorsChangedEvent;
  clips_changed: ClipsChangedEvent;
  recording_failed: RecordingFailedEvent;
  clip_failed: ClipFailedEvent;
  log_message: LogMessageEvent;
  request_show_window: RequestShowWindowEvent;
  timeline_changed: TimelineChangedEvent;
  export_started: ExportStartedEvent;
  export_progress: ExportProgressEvent;
  export_finished: ExportFinishedEvent;
  export_failed: ExportFailedEvent;
  onedrive_changed: OneDriveChangedEvent;
  onedrive_failed: OneDriveFailedEvent;
  request_received: RequestReceivedEvent;
  request_status_changed: RequestStatusChangedEvent;
  role_changed: RoleChangedEvent;
  transcode_started: TranscodeStartedEvent;
  transcode_progress: TranscodeProgressEvent;
  transcode_finished: TranscodeFinishedEvent;
  transcode_failed: TranscodeFailedEvent;
  encoder_restart_started: EncoderRestartStartedEvent;
  encoder_restart_finished: EncoderRestartFinishedEvent;
  encoder_restart_failed: EncoderRestartFailedEvent;
}

export type BackendEventName = keyof BackendEventMap;

// ── Analytics types (F4 — used by F5 AnalyticsTab) ──────────────────

export interface CountByClass {
  class_name: string;
  count: number;
}

export interface DwellRecord {
  track_id: number;
  class_name: string;
  total_seconds: number;
  first_seen: string;   // ISO-8601
  last_seen: string;    // ISO-8601
}

export interface AnalyticEventDTO {
  event_id: string;
  monitor_index: number;
  class_name: string;
  track_id: number;
  confidence: number;
  zone: string | null;
  timestamp: string;    // ISO-8601
}

// ── IPC envelope types ───────────────────────────────────────────────

export interface IpcRequest {
  id: string;
  cmd: string;
  payload: Record<string, unknown>;
}

export interface IpcResponse<T = unknown> {
  id: string;
  ok: boolean;
  result?: T;
  error?: string;
}
