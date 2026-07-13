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

// `AppPolicy` holds no `AppHandle`/Tauri runtime state — it's plain data behind
// an `RwLock`, so it's testable with `#[test]` directly, unlike `tray.rs`/
// `commands.rs` which need a real app handle (blocked on the documented
// `tauri::test::mock_app()` crash — see TODOS.md item 6; not chasing that fix,
// per the accepted pure-function-extraction pattern this module already follows).
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_empty_role_and_not_operator() {
        let policy = AppPolicy::default();
        assert_eq!(policy.role(), "");
        assert!(!policy.is_operator());
    }

    #[test]
    fn is_operator_true_only_for_operator_role() {
        let policy = AppPolicy::default();
        policy.set_role("operator");
        assert!(policy.is_operator());

        policy.set_role("it");
        assert!(!policy.is_operator());

        policy.set_role("supervisor");
        assert!(!policy.is_operator());
    }

    #[test]
    fn role_reflects_the_latest_set_role() {
        let policy = AppPolicy::default();
        policy.set_role("it");
        assert_eq!(policy.role(), "it");
        policy.set_role("operator");
        assert_eq!(policy.role(), "operator");
    }
}
