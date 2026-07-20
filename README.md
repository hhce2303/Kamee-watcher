# The Watcher

Always-on screen recorder with pre/post event capture, built for a Windows fleet
of Operator / IT / Supervisor roles. Python + FFmpeg headless backend (hexagonal
architecture) with a **Tauri 2.0 + React** desktop UI talking to it over an
authenticated named pipe.

The full product documentation — architecture, project structure, configuration,
build & install — lives in **[`project/README.md`](project/README.md)**.

## Quick links

- [**Onboarding**](ONBOARDING.md) — setup, dev mode, the 3 test suites, lint/CI, one path start to finish
- [Product README](project/README.md) — architecture, configuration, build & install
- [Migration docs](project/docs/migration/README.md) — QML/PySide6 → Tauri 2.0 + React,
  Python core → Rust hexagon (Track R)
- [Architecture decision records](project/docs/editing/adr/README.md)
- [`.env.example`](project/.env.example) — every supported environment variable
- [`TODOS.md`](TODOS.md) / [`CHANGELOG.md`](CHANGELOG.md) — current work and release history

## Repository layout

```
project/    Python core + backend, tests, docs
src/        React UI (TypeScript, Vite)
src-tauri/  Tauri 2.0 Rust shell
scripts/    Dev tooling (DTO codegen, etc.)
```

For setup instructions (Python venv, Rust toolchain, `npm install`, running in dev
mode, and the three test suites), see **[`ONBOARDING.md`](ONBOARDING.md)**.
