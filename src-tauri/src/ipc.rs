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
use tauri::Emitter;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::sync::{Mutex, oneshot};

const MAX_FRAME: usize = 32 * 1024 * 1024; // 32 MiB — matches Python guard

type PendingMap = Arc<Mutex<HashMap<String, oneshot::Sender<Result<Value, String>>>>>;

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
                if len > MAX_FRAME {
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

                // Response: route to the waiting caller by request id.
                if let Some(id) = msg.get("id").and_then(|v| v.as_str()) {
                    let waiter = pending_r.lock().await.remove(id);
                    if let Some(tx) = waiter {
                        let result = if msg.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
                            Ok(msg.get("result").cloned().unwrap_or(Value::Null))
                        } else {
                            let err = msg.get("error")
                                .and_then(|v| v.as_str())
                                .unwrap_or("unknown error")
                                .to_owned();
                            Err(err)
                        };
                        let _ = tx.send(result);
                    }
                    continue;
                }

                // Event: forward to the Tauri event bus so React can listen.
                if let Some(disc) = msg.get("event").and_then(|v| v.as_str()) {
                    let _ = app.emit(disc, &msg);
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
        let request = serde_json::json!({
            "id":      id,
            "cmd":     cmd,
            "payload": payload,
        });

        let body = serde_json::to_vec(&request).map_err(|e| e.to_string())?;
        let len  = (body.len() as u32).to_be_bytes();
        let mut frame = Vec::with_capacity(4 + body.len());
        frame.extend_from_slice(&len);
        frame.extend_from_slice(&body);

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
