//! Tauri commands exposed to the React frontend.
//!
//! `ipc_send` is the generic proxy: the JS layer calls `invoke("ipc_send", {cmd, payload})`
//! and this command forwards the frame to Python over the named pipe.  The response's
//! `result` field is returned on success; the `error` string is returned as an `Err`.
//!
//! Typed analytics commands delegate to the generic proxy so the Python router handles
//! all business logic — Rust stays a thin, type-safe transport layer.

use serde::Deserialize;
use serde_json::Value;
use tauri::State;

use crate::ipc::IpcState;

/// Generic IPC proxy — routes any backend command from JS through the pipe.
#[tauri::command]
pub async fn ipc_send(
    cmd:     String,
    payload: Value,
    state:   State<'_, IpcState>,
) -> Result<Value, String> {
    let guard = state.0.lock().await;
    let client = guard.as_ref().ok_or_else(|| "Backend not connected".to_string())?;
    client.send(&cmd, payload).await
}

/// Returns whether the named-pipe connection is currently live.
#[tauri::command]
pub async fn ipc_connected(state: State<'_, IpcState>) -> Result<bool, String> {
    Ok(state.0.lock().await.is_some())
}

// ── Analytics typed commands (Fase 5) ────────────────────────────────────────

/// Time-range + optional monitor filter shared by counts and dwell commands.
#[derive(Deserialize)]
pub struct AnalyticsFilter {
    pub since:         String,
    pub until:         String,
    pub monitor_index: Option<i64>,
}

/// Detection counts per class for the given time window.
#[tauri::command]
pub async fn analytics_counts(
    filter: AnalyticsFilter,
    state:  State<'_, IpcState>,
) -> Result<Value, String> {
    let payload = serde_json::json!({
        "since":         filter.since,
        "until":         filter.until,
        "monitor_index": filter.monitor_index,
    });
    let guard = state.0.lock().await;
    let client = guard.as_ref().ok_or_else(|| "Backend not connected".to_string())?;
    client.send("analytics_counts", payload).await
}

/// Cumulative dwell time per track_id for the given time window.
#[tauri::command]
pub async fn analytics_dwell(
    filter: AnalyticsFilter,
    state:  State<'_, IpcState>,
) -> Result<Value, String> {
    let payload = serde_json::json!({
        "since":         filter.since,
        "until":         filter.until,
        "monitor_index": filter.monitor_index,
    });
    let guard = state.0.lock().await;
    let client = guard.as_ref().ok_or_else(|| "Backend not connected".to_string())?;
    client.send("analytics_dwell", payload).await
}

/// All analytic events whose zone matches `zone_name` in the given time window.
#[derive(Deserialize)]
pub struct ZoneFilter {
    pub zone_name: String,
    pub since:     String,
    pub until:     String,
}

#[tauri::command]
pub async fn analytics_zone_events(
    filter: ZoneFilter,
    state:  State<'_, IpcState>,
) -> Result<Value, String> {
    let payload = serde_json::json!({
        "zone_name": filter.zone_name,
        "since":     filter.since,
        "until":     filter.until,
    });
    let guard = state.0.lock().await;
    let client = guard.as_ref().ok_or_else(|| "Backend not connected".to_string())?;
    client.send("analytics_zone_events", payload).await
}
