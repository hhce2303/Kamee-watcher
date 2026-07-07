---
description: >
  Use when creating or modifying adapters in app/adapters/. Covers FFmpeg subprocess
  patterns, named-pipe IPC router conventions, port-adapter contracts, and file naming for this
  project. PySide6/QML adapters (`app/adapters/ui/`) were removed in F3 (2026-07-06) — the UI is
  now Tauri 2.0 + React, talking to the backend only via `app/adapters/ipc/router.py`.
applyTo: "app/adapters/**/*.py"
---

# Adapter Conventions — The Watcher

## Port Contract

Every adapter must inherit exactly one port ABC from `app/core/ports/` and implement all abstract methods.

```python
from app.core.ports.recorder_port import RecorderPort

class FFmpegRecorderAdapter(RecorderPort):
    ...
```

## FFmpeg Adapters (`adapters/ffmpeg/`)

- Call FFmpeg/ffprobe via `subprocess` — **never** via `ffmpeg-python`.
- Always pass command as a `list`, never `shell=True`.
- Capture stderr for diagnostics. Use `loguru.logger` to log it.
- Segment output format is **MPEG-TS** (`.ts`), not `.mp4`. This is intentional — `.ts` requires no `moov` atom and survives crashes.
- Hardware encoder is resolved once at process startup by `encoder_selector.py` (NVENC → QSV → libx264). Reuse the cached result; do not re-probe.
- Monitor capture index (`output_idx`) comes from `MonitorInfo.dxgi_index`, not from the position of the monitor in `screeninfo`'s list.

```python
# Correct subprocess pattern
import subprocess
cmd = ["ffmpeg", "-f", "ddagrab", f"output_idx={monitor.dxgi_index}", ...]
proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
```

## Named-pipe IPC Adapter (`adapters/ipc/`)

- `router.py` is the only bridge between the frontend and `core/api`'s Facade — it must not
  contain business logic, only command dispatch (`cmd → Facade method`) and forwarding bus events
  to the pipe as `{event, ...fields}` envelopes.
- Every new command needs a matching entry in `src/lib/ipc.ts` and, if it's new domain data, a DTO
  in `core/api/dto.py` (regenerate `src/types/dto.gen.ts` via `npm run gen:dto`).
- Never stream video/preview frames through this channel — that goes through the Tauri
  `watcher://` custom protocol (TD-5), never JSON IPC.

## WebSocket Adapters (`adapters/ws/`)

- `request_server.py` / `request_client.py` implement the IT↔Supervisor clip-request protocol
  over `websockets` (asyncio-on-thread, Qt-free) — wire format is unchanged JSON text
  (`clip_request`/`ack`/`status_update`), so IT and Supervisor machines stay interoperable across
  rollout.
- `stop()` must schedule `loop.stop()` via `call_soon_threadsafe` **after** the shutdown future
  resolves, never from inside the shutdown coroutine itself — doing so races the future's
  resolution callback and causes a silent 5s hang on every teardown.

## Monitor Adapter (`adapters/monitor/`)

- `MonitorPort.list_monitors()` must return monitors in DXGI `EnumOutputs` order.
- Store both `screeninfo` display name (human-readable) and `dxgi_index` (for FFmpeg).
- Fingerprint monitors by `name + width + height + position` — indices can change after reboot.

## File Placement

| What | Where |
|------|-------|
| New FFmpeg-based adapter | `app/adapters/ffmpeg/{name}_adapter.py` |
| New UI widget | `app/adapters/ui/{widget_name}.py` |
| New port ABC | `app/core/ports/{domain}_port.py` |
| Wiring new adapter | `app/main.py` only |
