mod commands;
mod ipc;
mod media_protocol;
mod policy;
mod tray;

use ipc::{IpcState, ipc_connect_loop};
use media_protocol::MediaRootsState;
use policy::AppPolicy;
use tauri::{Manager, WindowEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Shared with the protocol handler below — both must see the same Arc so
    // a write from ipc.rs (after `get_media_roots`) is visible to `watcher://`.
    let media_roots = MediaRootsState::default();

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // A second launch (e.g. from the scheduled-task watchdog or a Start
            // Menu double-click) focuses the existing window instead of racing
            // for the named pipe with a second process.
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(IpcState::default())
        .manage(AppPolicy::default())
        .manage(media_roots.clone())
        .invoke_handler(tauri::generate_handler![
            commands::ipc_send,
            commands::ipc_connected,
            commands::analytics_counts,
            commands::analytics_dwell,
            commands::analytics_zone_events,
        ]);

    let builder = media_protocol::register(builder, media_roots);

    builder
        .setup(|app| {
            tray::setup(app.handle())?;

            let handle = app.handle().clone();
            let state: tauri::State<IpcState> = app.state();
            let ipc_state = state.inner().clone();
            tauri::async_runtime::spawn(ipc_connect_loop(ipc_state, handle));
            Ok(())
        })
        .on_window_event(|window, event| {
            // Operator's window is "indestructible" (ADR-0010): closing it hides
            // to tray instead of exiting, so recording survives. Enforced here
            // (not in JS) so the frontend cannot bypass the policy.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    let policy: tauri::State<AppPolicy> = window.state();
                    if policy.is_operator() {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
