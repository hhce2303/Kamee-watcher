"""Thread-safe event bus — the backbone that replaces Qt Signals (ADR-0009).

Why a dedicated bus
-------------------
Today the core pushes state to the UI through Qt Signals, which chains the whole
backend to Qt.  F1 replaces that with a transport-agnostic bus so QML *and* the
new ``adapters/ipc`` channel are interchangeable subscribers over one facade.

Threading model (documented contract — ADR-0009 flags deadlock/backpressure as
the F1 risk)
-------------------------------------------------------------------------------
Core callbacks fire on **background threads** — ``on_segment_finalized`` from the
FFmpeg watchdog thread, ``on_crash`` from the recorder supervisor, the monitor
detection poll thread, the OneDrive share worker.  If ``publish()`` ran
subscriber code inline it would run that code on those threads (and under
whatever lock the producer holds) — the classic deadlock.

So this bus decouples producer from consumer:

* ``publish(event)`` is callable from **any** thread.  It only enqueues onto a
  bounded internal queue and returns immediately — it never runs subscriber code.
* A single dedicated **dispatcher thread** drains the queue and invokes
  subscribers, in registration order, always on that one thread.  Every
  subscriber therefore has a single, predictable thread context.
* Subscribers must be **non-blocking**: they marshal to their own context — the
  QML adapter re-emits a queued Qt signal (hops to the Qt main thread); the IPC
  server does ``loop.call_soon_threadsafe`` onto its asyncio loop.  A subscriber
  that blocks stalls delivery for everyone — that is the contract, not a bug.

Backpressure
------------
The queue is bounded (default 2048).  ``publish`` never blocks a producer: on a
full queue it drops the **oldest** event and logs a throttled warning.  High-rate
coalescing events (recording-second ticks, preview revisions) tolerate drops;
consumers always re-read current state, so a lost tick is cosmetic.  A silent cap
would read as "everything delivered" — hence the explicit warning.

Tests can skip the thread entirely and call :meth:`EventBus.drain` to process the
queue synchronously for determinism.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from typing import Any, Callable, Optional

from loguru import logger

# A subscriber callback receives the event object and returns nothing.
EventCallback = Callable[[Any], None]

# Sentinel pushed onto the queue to wake the dispatcher for a clean shutdown.
_STOP = object()


@dataclass
class Subscription:
    """Handle returned by :meth:`EventBus.subscribe`; call :meth:`cancel` to stop."""

    _bus: "EventBus"
    _event_type: Optional[type]
    _callback: EventCallback
    _cancelled: bool = field(default=False)

    def cancel(self) -> None:
        if not self._cancelled:
            self._bus._remove(self)  # noqa: SLF001
            self._cancelled = True


class EventBus:
    """Bounded, thread-safe publish/subscribe with a single dispatcher thread."""

    def __init__(self, maxsize: int = 2048) -> None:
        self._queue: "Queue[Any]" = Queue(maxsize=maxsize)
        # Registry guarded by a short-lived lock; subscribers are invoked OUTSIDE
        # the lock (we snapshot the list) so a subscriber may itself publish or
        # (un)subscribe without deadlocking.
        self._subs_lock = threading.Lock()
        self._subscriptions: list[Subscription] = []
        self._dispatcher: Optional[threading.Thread] = None
        self._running = False
        # Overflow diagnostics — throttled so a flood does not spam the log.
        self._dropped = 0
        self._last_drop_log = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the dispatcher thread. Idempotent."""
        if self._running:
            return
        self._running = True
        self._dispatcher = threading.Thread(
            target=self._run, name="event-bus", daemon=True
        )
        self._dispatcher.start()
        logger.debug("[eventbus] dispatcher started (maxsize={}).", self._queue.maxsize)

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the dispatcher thread, draining what is already queued."""
        if not self._running:
            return
        self._running = False
        try:
            self._queue.put_nowait(_STOP)
        except Full:
            # Queue jammed — force a slot by discarding one, then signal stop.
            self._drop_oldest()
            try:
                self._queue.put_nowait(_STOP)
            except Full:
                pass
        if self._dispatcher is not None:
            self._dispatcher.join(timeout=timeout)
            self._dispatcher = None
        logger.debug("[eventbus] dispatcher stopped.")

    # ── Subscription ──────────────────────────────────────────────────

    def subscribe(
        self, event_type: Optional[type], callback: EventCallback
    ) -> Subscription:
        """Register *callback* for *event_type* (or all events when ``None``).

        Matching is by exact type or any base class (``isinstance``), so
        subscribing to a base event type also catches its subclasses.
        """
        sub = Subscription(self, event_type, callback)
        with self._subs_lock:
            self._subscriptions.append(sub)
        return sub

    def _remove(self, sub: Subscription) -> None:
        with self._subs_lock:
            try:
                self._subscriptions.remove(sub)
            except ValueError:
                pass

    # ── Publishing ────────────────────────────────────────────────────

    def publish(self, event: Any) -> None:
        """Enqueue *event* for delivery. Safe from any thread; never blocks."""
        try:
            self._queue.put_nowait(event)
        except Full:
            # Backpressure: make room by dropping the oldest, then enqueue.
            self._drop_oldest()
            try:
                self._queue.put_nowait(event)
            except Full:
                self._note_drop()

    def _drop_oldest(self) -> None:
        try:
            self._queue.get_nowait()
            self._note_drop()
        except Empty:
            pass

    def _note_drop(self) -> None:
        self._dropped += 1
        now = _monotonic()
        if now - self._last_drop_log >= 5.0:
            logger.warning(
                "[eventbus] queue full — dropped {} event(s) so far (backpressure).",
                self._dropped,
            )
            self._last_drop_log = now

    # ── Dispatch ──────────────────────────────────────────────────────

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                break
            self._dispatch(item)
        # Drain anything still queued at shutdown so no event is silently lost.
        self._drain_remaining()

    def _drain_remaining(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            if item is _STOP:
                continue
            self._dispatch(item)

    def _dispatch(self, event: Any) -> None:
        with self._subs_lock:
            targets = [
                s
                for s in self._subscriptions
                if s._event_type is None or isinstance(event, s._event_type)  # noqa: SLF001
            ]
        for sub in targets:
            try:
                sub._callback(event)  # noqa: SLF001
            except Exception:  # noqa: BLE001 — one bad subscriber must not kill the bus
                logger.exception(
                    "[eventbus] subscriber raised on {}", type(event).__name__
                )

    # ── Test / diagnostic helpers ─────────────────────────────────────

    def drain(self) -> int:
        """Synchronously dispatch every queued event (no dispatcher thread).

        Returns the number of events dispatched. For tests only — do not mix
        with a running dispatcher thread.
        """
        count = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            if item is _STOP:
                continue
            self._dispatch(item)
            count += 1
        return count

    @property
    def dropped(self) -> int:
        """Total events dropped to backpressure since construction."""
        return self._dropped


def _monotonic() -> float:
    # Wrapped so the module has one obvious clock source; time.monotonic() is
    # allowed in app code (only Date.now()/random are restricted in tooling).
    import time  # noqa: PLC0415

    return time.monotonic()
