//! `AppPolicy` — the role-derived state Rust needs OUTSIDE the JS layer:
//! whether the window-close should hide-to-tray (operator, "indestructible
//! window") or exit normally, and whether the tray shows a "Salir" item.
//!
//! Populated from the backend's `get_settings` snapshot right after the pipe
//! connects, and kept current by watching `role_changed` frames in the IPC
//! reader task (see `ipc.rs`).  Enforced in Rust, not JS, so the frontend
//! cannot bypass the operator close policy.

use std::sync::RwLock;

#[derive(Default)]
pub struct AppPolicy {
    role: RwLock<String>,
}

impl AppPolicy {
    pub fn role(&self) -> String {
        self.role.read().unwrap().clone()
    }

    pub fn set_role(&self, role: &str) {
        *self.role.write().unwrap() = role.to_string();
    }

    /// Operator's window survives close (hide-to-tray) per ADR-0010.
    pub fn is_operator(&self) -> bool {
        self.role() == "operator"
    }
}
