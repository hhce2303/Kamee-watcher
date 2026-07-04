"""HeadlessRuntime — run the backend without Qt (daemon / sidecar) (ADR-0010).

Orchestrates an already-built :class:`ApiLayer` + IPC pipe server: start the bus
and the pipe, then block until a stop signal, then tear down cleanly.  It is
transport/stack-agnostic (the pipe server and the ``on_stop`` teardown are
injected), so the lifecycle is fully unit-testable with fakes.

Exit codes: ``0`` clean stop; ``2`` the pipe could not bind (respawn guard — the
caller/watchdog must not spin-relaunch on a hard bind failure).
"""
from __future__ import annotations

import signal
import threading
from typing import Callable, Optional, TextIO

from loguru import logger

EXIT_OK = 0
EXIT_PIPE_BIND_FAILED = 2


class HeadlessRuntime:
    """Run bus + IPC pipe headless until stopped; clean teardown on exit."""

    def __init__(
        self,
        api_layer,
        pipe_server,
        *,
        on_stop: Optional[Callable[[], None]] = None,
        install_signals: bool = True,
    ) -> None:
        self._api = api_layer
        self._pipe = pipe_server
        self._on_stop = on_stop
        self._install_signals = install_signals
        self._stop = threading.Event()
        self._stopped = False

    # ── Public entrypoints ────────────────────────────────────────────

    def serve_daemon(self) -> int:
        """Operator daemon: run until a signal (window close never stops it)."""
        logger.info("[runtime] starting daemon (headless, decoupled).")
        return self._serve()

    def serve_sidecar(self, stdin: Optional[TextIO] = None) -> int:
        """IT/Supervisor sidecar: also stops on a stdin 'shutdown' line or EOF.

        TD-3: the Tauri parent cannot kill the Python process behind the
        PyInstaller bootloader, so it requests shutdown over stdin.
        """
        import sys  # noqa: PLC0415

        logger.info("[runtime] starting sidecar (headless, stdin shutdown).")
        watcher = threading.Thread(
            target=self._watch_stdin, args=(stdin or sys.stdin,), name="ipc-stdin", daemon=True
        )
        watcher.start()
        return self._serve()

    def request_stop(self) -> None:
        self._stop.set()

    # ── Core loop ─────────────────────────────────────────────────────

    def _serve(self) -> int:
        if self._install_signals:
            self._install_signal_handlers()
        self._api.start()
        try:
            self._pipe.start()
        except Exception:  # noqa: BLE001 — missing pywin32 / bad name
            logger.exception("[runtime] pipe server failed to start")
            self._teardown()
            return EXIT_PIPE_BIND_FAILED
        if not self._pipe.is_bound():
            logger.error("[runtime] IPC pipe did not bind — exiting (no respawn spin).")
            self._teardown()
            return EXIT_PIPE_BIND_FAILED
        logger.info("[runtime] serving on {}", self._pipe.pipe_name)
        self._stop.wait()
        self._teardown()
        return EXIT_OK

    def _teardown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        logger.info("[runtime] shutting down.")
        try:
            self._pipe.stop()
        except Exception:  # noqa: BLE001
            logger.exception("[runtime] pipe stop failed")
        try:
            self._api.stop()
        except Exception:  # noqa: BLE001
            logger.exception("[runtime] api stop failed")
        if self._on_stop is not None:
            try:
                self._on_stop()   # stops the recording stack → no orphan ffmpeg (TD-3)
            except Exception:  # noqa: BLE001
                logger.exception("[runtime] on_stop failed")

    # ── Signals / stdin ───────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        def _handler(_signum, _frame):
            self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass  # not on the main thread / unsupported — ignore

    def _watch_stdin(self, stdin: TextIO) -> None:
        try:
            while not self._stop.is_set():
                line = stdin.readline()
                if line == "":            # EOF — parent closed the pipe
                    logger.info("[runtime] stdin EOF — requesting shutdown.")
                    break
                if line.strip().lower() == "shutdown":
                    logger.info("[runtime] stdin shutdown command received.")
                    break
        except Exception:  # noqa: BLE001
            logger.exception("[runtime] stdin watcher error — requesting shutdown.")
        finally:
            self._stop.set()
