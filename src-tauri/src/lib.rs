mod commands;
mod ipc;

use ipc::{IpcState, ipc_connect_loop};
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(IpcState::default())
        .invoke_handler(tauri::generate_handler![
            commands::ipc_send,
            commands::ipc_connected,
            commands::analytics_counts,
            commands::analytics_dwell,
            commands::analytics_zone_events,
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            // Clone the managed state Arc so the connect loop owns it independently.
            let state: tauri::State<IpcState> = app.state();
            let ipc_state = state.inner().clone();
            tauri::async_runtime::spawn(ipc_connect_loop(ipc_state, handle));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
