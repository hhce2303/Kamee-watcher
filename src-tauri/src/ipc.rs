//! Named-pipe IPC client — connects to the Python backend (ADR-0011).
//!
//! Protocol: 4-byte big-endian unsigned length, then that many bytes of UTF-8 JSON.
//! Matches the Python `adapters/ipc/protocol.py` exactly.
//!
//! Frame routing on the read path:
//!   • `{"id": "…", "ok": …, "result": …}` → response: wakes the pending `send()` call.
//!   • `{"event": "…", …}`                  → backend event: forwarded to Tauri event bus.
//!
//! The server is single-client; this client reconnects automatically if the pipe closes.

use std::collections::HashMap;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::Value;
use tauri::{Emitter, Manager};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::sync::{Mutex, oneshot};

use crate::media_protocol::{MediaRoots, MediaRootsState};
use crate::policy::AppPolicy;
use crate::tray;

const MAX_FRAME: usize = 32 * 1024 * 1024; // 32 MiB — matches Python guard

type PendingMap = Arc<Mutex<HashMap<String, oneshot::Sender<Result<Value, String>>>>>;

/// A frame decoded off the wire, classified by shape.
///
/// Extracted as a pure function (no `AppHandle`/IO) so the routing logic —
/// the part that actually matters for ADR-0011's authenticated transport —
/// can be unit tested without a real Tauri runtime or named pipe.
enum ParsedFrame {
    /// `{"id": "…", "ok": …, "result"/"error": …}` — reply to a pending `send()`.
    Response { id: String, result: Result<Value, String> },
    /// `{"event": "…", …}` — backend-initiated event to forward.
    Event { name: String },
    /// Neither shape — has neither an `"id"` nor an `"event"` field.
    Unroutable,
}

fn classify_frame(msg: &Value) -> ParsedFrame {
    if let Some(id) = msg.get("id").and_then(|v| v.as_str()) {
        let result = if msg.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
            Ok(msg.get("result").cloned().unwrap_or(Value::Null))
        } else {
            let err = msg
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown error")
                .to_owned();
            Err(err)
        };
        return ParsedFrame::Response { id: id.to_owned(), result };
    }
    if let Some(name) = msg.get("event").and_then(|v| v.as_str()) {
        return ParsedFrame::Event { name: name.to_owned() };
    }
    ParsedFrame::Unroutable
}

/// Whether a declared incoming frame length exceeds the 32 MiB guard.
/// Extracted as a pure function so the exact boundary (`>` vs `>=`, off-by-one
/// on `MAX_FRAME` itself) is unit tested rather than only exercised inline.
fn frame_exceeds_limit(len: usize) -> bool {
    len > MAX_FRAME
}

/// Length-prefix a request frame: `cmd`/`payload` under request `id`.
fn encode_request(id: &str, cmd: &str, payload: &Value) -> Result<Vec<u8>, String> {
    let request = serde_json::json!({
        "id":      id,
        "cmd":     cmd,
        "payload": payload,
    });
    let body = serde_json::to_vec(&request).map_err(|e| e.to_string())?;
    let len = (body.len() as u32).to_be_bytes();
    let mut frame = Vec::with_capacity(4 + body.len());
    frame.extend_from_slice(&len);
    frame.extend_from_slice(&body);
    Ok(frame)
}

pub struct IpcClient {
    write_tx: tokio::sync::mpsc::Sender<Vec<u8>>,
    pending:  PendingMap,
    seq:      Arc<AtomicU64>,
}

impl IpcClient {
    /// Open the named pipe and start background reader/writer tasks.
    /// Returns `(client, disconnect_rx)` — `disconnect_rx` fires when the pipe closes.
    pub async fn connect(
        pipe_name: &str,
        app: tauri::AppHandle,
    ) -> anyhow::Result<(Self, oneshot::Receiver<()>)> {
        use tokio::net::windows::named_pipe::ClientOptions;

        let pipe = ClientOptions::new().open(pipe_name)?;
        let (mut reader, mut writer) = tokio::io::split(pipe);

        let pending: PendingMap = Arc::new(Mutex::new(HashMap::new()));
        let (write_tx, mut write_rx) = tokio::sync::mpsc::channel::<Vec<u8>>(256);
        let (disc_tx, disc_rx) = oneshot::channel::<()>();

        // Writer task — serialises all outbound frames onto the pipe.
        tokio::spawn(async move {
            while let Some(frame) = write_rx.recv().await {
                if writer.write_all(&frame).await.is_err() {
                    break;
                }
            }
        });

        // Reader task — demultiplexes responses and backend events.
        let pending_r = pending.clone();
        tokio::spawn(async move {
            let mut header = [0u8; 4];
            let mut body   = Vec::<u8>::new();

            loop {
                if reader.read_exact(&mut header).await.is_err() {
                    break;
                }
                let len = u32::from_be_bytes(header) as usize;
                if frame_exceeds_limit(len) {
                    log::error!("[ipc] frame too large ({len}), closing");
                    break;
                }
                body.resize(len, 0);
                if reader.read_exact(&mut body).await.is_err() {
                    break;
                }
                let Ok(msg) = serde_json::from_slice::<Value>(&body) else {
                    log::warn!("[ipc] malformed JSON frame, skipping");
                    continue;
                };

                match classify_frame(&msg) {
                    ParsedFrame::Response { id, result } => {
                        let waiter = pending_r.lock().await.remove(&id);
                        if let Some(tx) = waiter {
                            let _ = tx.send(result);
                        }
                    }
                    ParsedFrame::Event { name } => {
                        // Forward to the Tauri event bus so React can listen.
                        match name.as_str() {
                            "role_changed" => {
                                if let Some(role) = msg.get("role").and_then(|v| v.as_str()) {
                                    if let Some(policy) = app.try_state::<AppPolicy>() {
                                        policy.set_role(role);
                                    }
                                    tray::rebuild_menu(&app, role);
                                }
                            }
                            "recording_state_changed" => {
                                let active = msg
                                    .get("state")
                                    .and_then(|s| s.get("is_recording"))
                                    .and_then(|v| v.as_bool())
                                    .unwrap_or(false);
                                tray::set_recording_active(&app, active);
                            }
                            _ => {}
                        }
                        let _ = app.emit(&name, &msg);
                    }
                    ParsedFrame::Unroutable => {}
                }
            }

            // Drain pending requests on disconnect.
            let mut locked = pending_r.lock().await;
            for (_, tx) in locked.drain() {
                let _ = tx.send(Err("IPC disconnected".into()));
            }
            let _ = disc_tx.send(());
            log::info!("[ipc] reader exited");
        });

        Ok((
            Self {
                write_tx,
                pending,
                seq: Arc::new(AtomicU64::new(1)),
            },
            disc_rx,
        ))
    }

    /// Send a command to the Python backend and await the response.
    pub async fn send(&self, cmd: &str, payload: Value) -> Result<Value, String> {
        let id = self.seq.fetch_add(1, Ordering::Relaxed).to_string();
        let frame = encode_request(&id, cmd, &payload)?;

        let (tx, rx) = oneshot::channel();
        self.pending.lock().await.insert(id, tx);
        self.write_tx.send(frame).await.map_err(|e| e.to_string())?;

        rx.await.map_err(|e| e.to_string())?
    }
}

// ── Managed state ────────────────────────────────────────────────────

/// Tauri-managed IPC state. `None` when the pipe is not connected.
#[derive(Clone, Default)]
pub struct IpcState(pub Arc<Mutex<Option<IpcClient>>>);

/// Background task: connect to the pipe, keep state updated, reconnect on drop.
pub async fn ipc_connect_loop(state: IpcState, app: tauri::AppHandle) {
    use std::time::Duration;

    let user = std::env::var("USERNAME").unwrap_or_else(|_| "default".to_string());
    let pipe_name = format!(r"\\.\pipe\TheWatcher.{user}");
    log::info!("[ipc] connecting to {pipe_name}");

    loop {
        match IpcClient::connect(&pipe_name, app.clone()).await {
            Ok((client, disc_rx)) => {
                log::info!("[ipc] connected");

                // Fetch the role/settings snapshot and the media-protocol allowlist
                // now that the pipe is up — both are needed before the UI can trust
                // the tray label or the custom protocol can serve any file.
                if let Ok(settings) = client.send("get_settings", Value::Object(Default::default())).await {
                    if let Some(role) = settings.get("role").and_then(|v| v.as_str()) {
                        if let Some(policy) = app.try_state::<AppPolicy>() {
                            policy.set_role(role);
                        }
                        tray::rebuild_menu(&app, role);
                    }
                }
                if let Ok(roots_json) = client.send("get_media_roots", Value::Object(Default::default())).await {
                    if let Some(roots) = MediaRoots::from_json(&roots_json) {
                        if let Some(state) = app.try_state::<MediaRootsState>() {
                            *state.0.write().await = Some(roots);
                        }
                    }
                }

                *state.0.lock().await = Some(client);
                let _ = app.emit("ipc_connected", true);

                // Block until the pipe closes.
                let _ = disc_rx.await;
                *state.0.lock().await = None;
                let _ = app.emit("ipc_disconnected", ());
                log::info!("[ipc] disconnected — will retry in 2s");
            }
            Err(e) => {
                log::debug!("[ipc] connect failed: {e} — retry in 2s");
            }
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
    }
}

// ── Tests ────────────────────────────────────────────────────────────────
//
// Pure unit tests against the extracted protocol logic (frame classification
// + request encoding) — the properties that matter for ADR-0011's
// authenticated transport (response routing by id, error propagation,
// oversized/malformed-frame rejection) without needing a real Tauri
// AppHandle, named pipe, or tokio runtime at all.
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_frame_routes_successful_response_by_id() {
        let msg = serde_json::json!({"id": "7", "ok": true, "result": {"role": "operator"}});
        match classify_frame(&msg) {
            ParsedFrame::Response { id, result } => {
                assert_eq!(id, "7");
                assert_eq!(result.unwrap()["role"], "operator");
            }
            _ => panic!("expected Response"),
        }
    }

    #[test]
    fn classify_frame_missing_result_defaults_to_null() {
        let msg = serde_json::json!({"id": "1", "ok": true});
        match classify_frame(&msg) {
            ParsedFrame::Response { result, .. } => assert_eq!(result.unwrap(), Value::Null),
            _ => panic!("expected Response"),
        }
    }

    #[test]
    fn classify_frame_propagates_server_error_message() {
        let msg = serde_json::json!({"id": "9", "ok": false, "error": "unknown command"});
        match classify_frame(&msg) {
            ParsedFrame::Response { id, result } => {
                assert_eq!(id, "9");
                assert_eq!(result, Err("unknown command".to_string()));
            }
            _ => panic!("expected Response"),
        }
    }

    #[test]
    fn classify_frame_missing_error_field_uses_fallback_message() {
        let msg = serde_json::json!({"id": "9", "ok": false});
        match classify_frame(&msg) {
            ParsedFrame::Response { result, .. } => {
                assert_eq!(result, Err("unknown error".to_string()));
            }
            _ => panic!("expected Response"),
        }
    }

    #[test]
    fn classify_frame_recognises_event_shape() {
        let msg = serde_json::json!({"event": "recording_state_changed", "state": {"is_recording": true}});
        match classify_frame(&msg) {
            ParsedFrame::Event { name } => assert_eq!(name, "recording_state_changed"),
            _ => panic!("expected Event"),
        }
    }

    #[test]
    fn classify_frame_neither_id_nor_event_is_unroutable() {
        let msg = serde_json::json!({"unexpected": "shape"});
        assert!(matches!(classify_frame(&msg), ParsedFrame::Unroutable));
    }

    #[test]
    fn classify_frame_id_takes_priority_over_event() {
        // A frame can't legitimately be both, but if it were, response routing
        // must win — an in-flight caller waiting on this id must not hang.
        let msg = serde_json::json!({"id": "1", "ok": true, "event": "should_be_ignored"});
        assert!(matches!(classify_frame(&msg), ParsedFrame::Response { .. }));
    }

    #[test]
    fn encode_request_produces_correct_length_prefix() {
        let frame = encode_request("42", "get_settings", &Value::Object(Default::default())).unwrap();
        let declared_len = u32::from_be_bytes(frame[0..4].try_into().unwrap()) as usize;
        assert_eq!(declared_len, frame.len() - 4);

        let body: Value = serde_json::from_slice(&frame[4..]).unwrap();
        assert_eq!(body["id"], "42");
        assert_eq!(body["cmd"], "get_settings");
    }

    #[test]
    fn encode_request_embeds_payload_verbatim() {
        let payload = serde_json::json!({"monitor_index": 1, "path": "C:/clips/a.mp4"});
        let frame = encode_request("1", "trim_clip", &payload).unwrap();
        let body: Value = serde_json::from_slice(&frame[4..]).unwrap();
        assert_eq!(body["payload"], payload);
    }

    #[test]
    fn frame_exceeds_limit_boundary() {
        assert!(!frame_exceeds_limit(MAX_FRAME));
        assert!(frame_exceeds_limit(MAX_FRAME + 1));
        assert!(!frame_exceeds_limit(0));
    }

    #[test]
    fn max_frame_is_32_mib() {
        // Pins the value itself (not just the boundary check above) so an
        // accidental edit to the constant is caught here rather than only
        // surfacing as a cross-process interop failure against
        // `adapters/ipc/protocol.py`'s matching guard. This test cannot
        // verify the Python side directly — that requires exercising the
        // real pipe (see the malformed/oversized-frame path, which is
        // exercised in practice via manual testing against the Python
        // server, not from this pure unit test).
        assert_eq!(MAX_FRAME, 32 * 1024 * 1024);
    }
}
