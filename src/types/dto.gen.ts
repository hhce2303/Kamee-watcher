export interface DtoSchema {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "AddClip".
 */
export interface AddClip {
  duration_s: number;
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "AddClipTrimmed".
 */
export interface AddClipTrimmed {
  duration_s: number;
  in_frac: number;
  out_frac: number;
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "AddFilesFromUrls".
 */
export interface AddFilesFromUrls {
  urls: string[];
}
/**
 * Base for every bus event. ``event`` is the wire discriminator.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "BaseEvent".
 */
export interface BaseEvent {
  event: string;
}
/**
 * A clip file listed in the clips browser.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ClipDTO".
 */
export interface ClipDTO {
  clip_name: string;
  date_label: string;
  is_event: boolean;
  path: string;
  size_label: string;
}
/**
 * One trimmed clip on the evidence reel — mirrors core/editor/models.ClipEntry.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ClipEntryDTO".
 */
export interface ClipEntryDTO {
  in_point_s: number;
  out_point_s: number;
  source_duration_s: number;
  source_path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ClipFailed".
 */
export interface ClipFailed {
  event?: "clip_failed";
  message: string;
}
/**
 * Media metadata for the currently loaded clip (from PlayerService).
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ClipInfoDTO".
 */
export interface ClipInfoDTO {
  bitrate?: string;
  codec?: string;
  duration_seconds?: number;
  fps?: string;
  resolution?: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ClipsChanged".
 */
export interface ClipsChanged {
  clips: ClipDTO[];
  event?: "clips_changed";
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "EncoderRestartFailed".
 */
export interface EncoderRestartFailed {
  event?: "encoder_restart_failed";
  message: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "EncoderRestartFinished".
 */
export interface EncoderRestartFinished {
  event?: "encoder_restart_finished";
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "EncoderRestartStarted".
 */
export interface EncoderRestartStarted {
  event?: "encoder_restart_started";
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "EnsureFolderLink".
 */
export interface EnsureFolderLink {
  folder_path?: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ExportFailed".
 */
export interface ExportFailed {
  event?: "export_failed";
  message: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ExportFinished".
 */
export interface ExportFinished {
  event?: "export_finished";
  output_path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ExportProgress".
 */
export interface ExportProgress {
  event?: "export_progress";
  fraction: number;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ExportStarted".
 */
export interface ExportStarted {
  event?: "export_started";
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ExportTimeline".
 */
export interface ExportTimeline {
  output_path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ListAllOperators".
 */
export interface ListAllOperators {}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ListDirectory".
 */
export interface ListDirectory {
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ListOperators".
 */
export interface ListOperators {
  storage_path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ListStorages".
 */
export interface ListStorages {}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "LoadClip".
 */
export interface LoadClip {
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "LogMessage".
 */
export interface LogMessage {
  event?: "log_message";
  message: string;
}
/**
 * Filesystem roots the UI's custom media protocol is allowed to serve from.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "MediaRoots".
 */
export interface MediaRoots {
  clips_dir: string;
  segments_dir: string;
  storage_roots?: string[];
}
/**
 * A monitor as the UI sees it — mirrors AppBridge.monitors item shape.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "MonitorDTO".
 */
export interface MonitorDTO {
  device_name: string;
  fingerprint: string;
  index: number;
  is_primary: boolean;
  name: string;
  resolution: string;
  selected: boolean;
  x: number;
  y: number;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "MonitorsChanged".
 */
export interface MonitorsChanged {
  event?: "monitors_changed";
  monitors: MonitorDTO[];
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "OneDriveChanged".
 */
export interface OneDriveChanged {
  event?: "onedrive_changed";
  folder?: string;
  link?: string;
  state: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "OneDriveFailed".
 */
export interface OneDriveFailed {
  event?: "onedrive_failed";
  message: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "OpenItWsPort".
 */
export interface OpenItWsPort {}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "RecordingFailed".
 */
export interface RecordingFailed {
  event?: "recording_failed";
  message: string;
}
/**
 * Snapshot of the recording subsystem — replaces polled bridge properties.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "RecordingState".
 */
export interface RecordingState {
  event_count?: number;
  is_recording?: boolean;
  record_seconds?: number;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "RecordingStateChanged".
 */
export interface RecordingStateChanged {
  event?: "recording_state_changed";
  state: RecordingState;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "RequestReceived".
 */
export interface RequestReceived {
  event?: "request_received";
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "RequestShowWindow".
 */
export interface RequestShowWindow {
  event?: "request_show_window";
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "RequestStatusChanged".
 */
export interface RequestStatusChanged {
  event?: "request_status_changed";
  request_id: string;
  status: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "RoleChanged".
 */
export interface RoleChanged {
  event?: "role_changed";
  it_unlocked?: boolean;
  role: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SendClipRequest".
 */
export interface SendClipRequest {
  request_json: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SetAutorecord".
 */
export interface SetAutorecord {
  enabled: boolean;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SetAutostart".
 */
export interface SetAutostart {
  enabled: boolean;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SetClipsDir".
 */
export interface SetClipsDir {
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SetCodec".
 */
export interface SetCodec {
  codec: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SetDriverIndex".
 */
export interface SetDriverIndex {
  index: number;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SetRole".
 */
export interface SetRole {
  origin?: string;
  role: string;
}
/**
 * Full settings/role state for the UI shell — replaces polled bridge getters.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "SettingsSnapshot".
 */
export interface SettingsSnapshot {
  autorecord: boolean;
  autostart: boolean;
  clips_dir: string;
  codec: string;
  driver: string;
  it_unlocked: boolean;
  role: string;
}
/**
 * Outcome of the OneDrive folder+link flow.
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ShareResultDTO".
 */
export interface ShareResultDTO {
  folder_path: string;
  share_link: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "StartRecording".
 */
export interface StartRecording {
  origin?: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "StopRecording".
 */
export interface StopRecording {
  origin?: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "TimelineChanged".
 */
export interface TimelineChanged {
  event?: "timeline_changed";
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "ToggleMonitor".
 */
export interface ToggleMonitor {
  fingerprint: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "TranscodeClip".
 */
export interface TranscodeClip {
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "TranscodeFailed".
 */
export interface TranscodeFailed {
  event?: "transcode_failed";
  message: string;
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "TranscodeFinished".
 */
export interface TranscodeFinished {
  event?: "transcode_finished";
  output_path: string;
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "TranscodeProgress".
 */
export interface TranscodeProgress {
  event?: "transcode_progress";
  fraction: number;
  path: string;
}
/**
 * HEVC→H.264 on-demand transcode for playback (TD-1: WebView2 has no SW HEVC).
 *
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "TranscodeStarted".
 */
export interface TranscodeStarted {
  event?: "transcode_started";
  path: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "TriggerEvent".
 */
export interface TriggerEvent {
  origin?: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "UnlockIT".
 */
export interface UnlockIT {
  origin?: string;
  pin: string;
}
/**
 * This interface was referenced by `DtoSchema`'s JSON-Schema
 * via the `definition` "UpdateRequestStatus".
 */
export interface UpdateRequestStatus {
  request_id: string;
  status: string;
}
