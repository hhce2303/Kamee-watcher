/**
 * TypeScript mirror of project/app/core/api/dto.py (ADR-0009).
 *
 * Keep in sync with the Python source. These types reflect the JSON that
 * the IPC framing layer (adapters/ipc/protocol.py) serialises over the pipe.
 * Field names are snake_case to match Python model_dump() output verbatim.
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

// ── Event DTOs (backend → UI push) ──────────────────────────────────

export interface BaseEvent {
  event: string;
}

export interface RecordingStateChangedEvent extends BaseEvent {
  event: "RecordingStateChanged";
  is_recording: boolean;
  record_seconds: number;
  event_count: number;
}

export interface MonitorsChangedEvent extends BaseEvent {
  event: "MonitorsChanged";
  monitors: MonitorDTO[];
}

export interface ClipsChangedEvent extends BaseEvent {
  event: "ClipsChanged";
  clips: ClipDTO[];
}

export interface ExportProgressEvent extends BaseEvent {
  event: "ExportProgress";
  progress: number;
}

export interface ExportFinishedEvent extends BaseEvent {
  event: "ExportFinished";
  output_path: string;
}

export interface ExportFailedEvent extends BaseEvent {
  event: "ExportFailed";
  error: string;
}

export interface LogMessageEvent extends BaseEvent {
  event: "LogMessage";
  message: string;
}

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
