# TODOS

## Operator policy engine — deferred follow-ups
Captured during `/plan-eng-review` of `feat/operator-policy-engine` (2026-06-23).
All three were consciously deferred to keep this PR right-sized; each has a clear
trigger to pick it up.

### 1. Hang / liveness detection for the operator process
- **What:** Detect and recover a *hung-but-alive* operator process (frozen main
  loop — the operator process is now the headless Python daemon post-F1/F3, not
  the old Qt event loop) — add a heartbeat (the app writes a timestamp; a
  checker relaunches if stale) or a watchdog execution-time-limit.
- **Why:** The current restart watchdog is a Windows Scheduled Task with
  *restart-on-failure*. It only fires when the process *exits* with a non-zero
  result (kill / crash). A process that is alive but wedged never exits, so the
  scheduler never restarts it and recording silently stops.
- **Pros:** Closes the last always-on gap.
- **Cons:** Reintroduces the polling/heartbeat machinery the native-scheduler
  approach deliberately avoided; risk of false-positive relaunches during heavy
  disk I/O or FFmpeg stalls.
- **Context:** The common hang (FFmpeg stall) is already handled in-process by
  `RecorderSupervisor` (`app/core/recording_service/supervisor.py`) plus
  `recording_health`. This TODO is only for a *full-app* freeze, which is rarer.
- **Depends on:** the scheduled-task watchdog (`app/infrastructure/scheduled_task.py`).

### 2. Report degraded watchdog state to IT (remote)
- **What:** When the scheduled-task registration fails (corporate group policy /
  permissions) and the app falls back to the HKCU Run key, push that degraded
  state to IT over the existing request WebSocket / inbox — not just a log line.
- **Why:** On a locked-down box the operator has no settings tab and may never
  see a log file. IT should know which stations lack restart-after-kill
  protection (fleet health).
- **Pros:** IT visibility into degraded stations.
- **Cons:** Couples a log/status concern to the WS/inbox plumbing for a rare case.
- **Context:** `enforce_role` returns `"runkey"` in this case (see
  `app/core/role.py`). Post-F3, `main.py` only logs this
  (`logger.info("Role: {} | watchdog: {}", ...)`) — the old Python tray tooltip
  (`app/adapters/ui/tray_icon.py`) that used to surface it was removed with
  QML/PySide6; the new Rust tray (`src-tauri/src/tray.rs`) does not yet surface
  watchdog status either, so this is currently invisible outside the log file.
  The WS server/client live in `app/adapters/ws/`.
- **Depends on:** the request system (IT server / Supervisor client).

## Ship follow-ups — feat/f1-backend-headless → main (2026-07-10)
Captured during `/ship` of the F1–F3 migration branch (backend headless, full
React+Tauri UI, Rust segment engine, MJPEG preview server) plus this session's
recording-health/hourly-clip fix. Deferred to keep the ship moving; each has a
clear trigger to pick it up.

### 4. CI/release pipeline for the Tauri installer + Rust native module
- **What:** No `.github/workflows/` exists yet. This branch introduces two new
  distributable artifacts — the Tauri desktop shell (`src-tauri/`) and the
  native Rust segment engine (`project/native/watcher_segments`, built via
  `maturin`) — with no automated build/release pipeline for either.
- **Why:** Already flagged in `CLAUDE.md` (repo root) as a known remaining item
  ("Tauri prod installer packaging queda como fase posterior a F3"). Not a
  surprise, but worth a durable tracker now that the branch is landing.
- **Pros:** Reproducible signed installers (MSI/NSIS via `tauri-action`),
  catches native-build breakage in CI instead of on a dev machine.
- **Context:** `tauri-action` is the standard GitHub Actions integration;
  `maturin` is already wired into `setup_env.ps1` / `installer/build.ps1`
  per the Rust F0 spike.
- **Depends on:** —

### 5. Test coverage gaps in the React UI and Tauri Rust shell
- **What:** AI-assessed coverage audit at ship time: ~55% weighted by risk.
  Closed in this ship: `ipc.rs` (10 unit tests on the extracted
  frame-classification/encoding/frame-limit logic) and `LogDrawer`/`LogTicker`
  (render tests added during Fix-First triage, plus a shared
  `LOG_LEVEL_STYLE` map replacing the duplicated per-component branching).
  Remaining gaps:
  - 38 of the 39 new React component/feature/shell files (editor/trim/export
    flow, `ITEditorView`, `SupervisorView`, `AnalyticsTab`, most of
    `src/shell/*`) have no component test.
  - 9 of 14 new frontend hooks are untested: `useClipTranscode`,
    `useEditorExport`, `useInboxRequests`, `useLiveAnalytics`, `useMediaRoots`,
    `useRequests`, `useSettingsForm`, `useStorages`, `useTauriEvent`/`useIpc`.
  - `src-tauri/src/{commands,policy,tray,lib}.rs` have no `#[test]`s (only
    `media_protocol.rs` and `ipc.rs` do).
- **Why:** Untested paths are where regressions hide silently, especially in
  the frame-exact editor/export flow (already flagged as tricky in TD-7).
- **Pros:** Closes the highest-remaining-risk gap; the backend Python suite
  is already at ~90% module-to-test mapping, so this brings the frontend/Rust
  shell up to the same bar.
- **Cons:** Non-trivial effort — component tests for the editor/export flow
  need a render harness; the Rust command layer needs a `tauri::test`
  approach that doesn't hit the `MockRuntime` linking issue found this
  session (see item 6).
- **Depends on:** item 6 if the Rust command layer is tackled with
  `tauri::test::mock_app()`.

### 6. `tauri::test::mock_app()` crashes the test binary on this machine
- **What:** Adding `tauri = { features = ["test"] }` as a dev-dependency and
  calling `tauri::test::mock_app()` from a `#[tokio::test]` compiles cleanly
  but the resulting test executable crashes at startup with
  `STATUS_ENTRYPOINT_NOT_FOUND` (0xc0000139) — reproducible, affects the
  *entire* test binary (including previously-passing `media_protocol.rs`
  tests), both in `--release` and debug profile.
- **Why:** Investigated during this ship's `ipc.rs` coverage work; root cause
  not identified (looks like a DLL/feature-unification interaction between
  the `test` feature and the real `tray-icon`/`image-png` GUI features
  compiled into the same binary — possibly a stale/mismatched native
  WebView2 dependency). Worked around by extracting the pure protocol logic
  (frame classification, request encoding) into free functions and testing
  those directly with plain `#[test]`, avoiding `AppHandle` entirely.
- **Pros of investigating:** Unblocks proper `tauri::test`-based command/IPC
  integration testing (needed for item 5's Rust command-layer gap).
- **Cons:** Environment-specific Windows/Tauri toolchain issue, could be a
  rabbit hole; the workaround (pure-function extraction) is a reasonable
  permanent pattern regardless.
- **Context:** repro is `cargo test --release` in `src-tauri/` with
  `tauri = { version = "2", features = [...original features..., "test"] }`
  added under `[dev-dependencies]`.
- **Depends on:** —

### 7. Manual QA for the recording-health visibility fix (this session)
- **What:** Two manual verification steps from this session's plan were not
  run live (accepted with automated-test coverage as a substitute):
  1. Kill a monitor's ffmpeg mid-build with the app running — confirm the
     orphaned `.tmp.mp4` disappears on the next segment cycle instead of
     persisting until app restart.
  2. Force a worker into `RECOVERING` (kill the live recorder's ffmpeg, not
     a build) — confirm a "warning"-level entry appears in the frontend
     LogDrawer, and a recovery entry on stabilization.
- **Why:** `test_hourly_recording_builder_purge.py` and
  `test_recording_health_service.py` + `appStore.test.ts` cover the logic in
  isolation but not the true end-to-end live-app flow.
- **Context:** see `project/app/adapters/ffmpeg/hourly_recording_builder.py`
  (`_purge_stale_temps`) and `project/app/core/recording_health/service.py`
  (`set_callbacks`).
- **Depends on:** running the real app with a live recorder.

### 8. Negative-case test for a truncated preview JPEG
- **What:** `_read_valid_jpeg()` (`mjpeg_server_adapter.py`) requires both the
  SOI (`\xff\xd8`) and EOI (`\xff\xd9`) markers — discovered while fixing the
  test fixtures in `test_preview_server.py` (they were missing the EOI byte,
  which caused a real test hang this session, see the ship diagnosis).
  No test covers the actual real-world case this validation guards against:
  a `preview.jpg` truncated mid-write by FFmpeg (present on disk, missing the
  EOI marker) — confirm the snapshot endpoint 404s/retries and the MJPEG
  stream skips that frame instead of serving a corrupt one.
- **Why:** Lowest-priority item from this ship's pre-landing review
  (confidence 4/10 — appendix-tier, not blocking); flagged for completeness
  rather than fixed inline to keep the ship moving.
- **Context:** `project/tests/test_preview_server.py`,
  `project/app/adapters/preview_server/mjpeg_server_adapter.py:99-120`.
- **Depends on:** —

## Completed

### Track R2 — recorder supervision: ctypes orphan-fix, M1 clip-engine quick win, M5 hardening
- **What:** Full-scope investigation of the Rust recorder-supervision migration plan
  (`/plan-eng-review`'d 2026-07-11, branch `feat/f1-backend-headless`). Delivered: M0 (bench
  harness + full-scale legacy/auto baseline, 3 real monitors), the ctypes orphan-fix (spawn
  suspended → assign to Job → resume, closing the historical Popen-then-assign race in
  `recorder_adapter.py`/`process_guard.py`), M1 (`allow_threads` GIL fix in the Rust
  `compile_clip`, `CLIP_ENGINE` routing with automatic FFmpeg fallback), and M5 (`ClipBuilder`'s
  0.5s sleep-poll replaced with a `threading.Condition`, plus the ADR-0007 SLA gate resolved).
- **Why:** M2a's ctypes-vs-Rust spike (`project/tools/spike_m2a_ctypes_guard.py`) proved pure
  ctypes closes the FFmpeg-orphan race just as well as the planned Rust crate (0/500 in a rapid
  spawn+kill race test, a clean hard-kill/Job-reap test) — reusing structs already shipped in
  `process_guard.py`. User decided to close the cycle there rather than spend 5+ more weeks on
  the `watcher_recorder_guard` Rust crate (M2), its directory-watcher + parity harness (M3), and
  the wire-in + 24h soak (M4) — all **deferred indefinitely**, so `RECORDER_GUARD` is never
  introduced and there is no second supervision implementation to later remove (this is why the
  original item #9 here, "remove the legacy Python watchdog after `RECORDER_GUARD=auto` proves
  stable," no longer applies — that flag never ships).
- **Context:** Decision record: [ADR-0016](project/docs/editing/adr/ADR-0016-recorder-supervision-ctypes-not-rust.md)
  (ctypes not Rust) and [ADR-0017](project/docs/editing/adr/ADR-0017-adr0007-sla-verdict-confirmed.md)
  (ADR-0007 SLA gate: PASS, Track R3 not triggered — zero-copy capture CPU is 1.06-1.19% of this
  16-core machine per monitor, well under the 5% SLA). Full telemetry and methodology:
  `project/docs/migration/track-r2-baseline.md` and `track-r2-m2a-decision.md`. New tests:
  `test_process_guard.py::TestResumeSuspendedProcess`, `test_parity_clip_port.py`,
  `test_clip_builder_condition_regression.py`, plus extensions to `test_proc_telemetry.py` and
  `test_bench_report.py`.
- **If revisited:** only if poll-based crash/stall detection (~1s crash, ~360s stall at production
  segment durations) proves to be a real operational problem (not theoretical) — reopens with a
  fresh spike/ADR, same reopening pattern as ADR-0007 (DXGI capture).
- **Completed:** 2026-07-11 (branch `feat/f1-backend-headless`)

### Audit log for IT unlocks and role changes
- **What:** Persist an audit trail (who / when / which machine) for IT-PIN
  unlocks (`Ctrl+Alt+Shift+R`) and role changes (`setRole`).
- **Why:** The IT PIN is the *sole* gate — anyone holding it can unlock on any
  machine. For a security/monitoring tool, traceability of privilege use matters.
- **Context:** Implemented as `AuditPort` (`app/core/ports/audit_port.py`,
  ADR-0011) — `SettingsApi.set_role` / `SettingsApi.unlock_it`
  (`app/core/api/settings_api.py`) call `_audit_cmd()` for every attempt
  (success and failure), persisted via `sqlite_event_store.py`. Covered by
  `project/tests/test_audit_store.py`.
- **Completed:** v0.1.0 (2026-07-10)
