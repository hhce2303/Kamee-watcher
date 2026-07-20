//! System tray (replaces the Qt `QSystemTrayIcon` in `adapters/ui/tray_icon.py`).
//!
//! Menu is rebuilt whenever the role changes (operator gets no "Salir" item —
//! the window-close policy in `lib.rs` already hides instead of exiting for
//! that role, so removing the menu item too avoids a second way out).
//! Tooltip/state icon react to `recording_state_changed` frames observed by
//! the IPC reader task (see `ipc.rs`).

use tauri::menu::{Menu, MenuBuilder, MenuItem, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Runtime};

use crate::policy::AppPolicy;

const SHOW_ID: &str = "tray_show";
const EXIT_ID: &str = "tray_exit";

fn build_menu<R: Runtime>(app: &AppHandle<R>, role: &str) -> tauri::Result<Menu<R>> {
    let show: MenuItem<R> = MenuItemBuilder::with_id(SHOW_ID, "Abrir panel").build(app)?;
    let mut builder = MenuBuilder::new(app).item(&show);
    // Operator's window is "indestructible" (ADR-0010) — no tray exit for that role.
    if role != "operator" {
        builder = builder.separator();
        let exit: MenuItem<R> = MenuItemBuilder::with_id(EXIT_ID, "Salir").build(app)?;
        builder = builder.item(&exit);
    }
    builder.build()
}

pub fn setup<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let Some(icon) = app.default_window_icon().cloned() else {
        log::error!("[tray] no default window icon configured — skipping tray setup");
        return Ok(());
    };

    let policy: tauri::State<AppPolicy> = app.state();
    let role = policy.role();
    let menu = build_menu(app, &role)?;

    let handle = app.clone();
    TrayIconBuilder::with_id("main")
        .menu(&menu)
        .tooltip("The Watcher")
        .icon(icon)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            SHOW_ID => show_main(app),
            EXIT_ID => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                show_main(tray.app_handle());
            }
        })
        .build(&handle)?;
    Ok(())
}

fn show_main<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// Rebuild the tray menu after a `role_changed` event (operator ⇄ other roles
/// toggles whether "Salir" is present).
pub fn rebuild_menu<R: Runtime>(app: &AppHandle<R>, role: &str) {
    let Some(tray) = app.tray_by_id("main") else { return };
    if let Ok(menu) = build_menu(app, role) {
        let _ = tray.set_menu(Some(menu));
    }
}

/// Reflect live recording state in the tray tooltip.
pub fn set_recording_active<R: Runtime>(app: &AppHandle<R>, active: bool) {
    let Some(tray) = app.tray_by_id("main") else { return };
    let tooltip = if active { "The Watcher — Grabando" } else { "The Watcher" };
    let _ = tray.set_tooltip(Some(tooltip));
}
