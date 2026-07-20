"""EventBus — thread-safety, ordering, backpressure, and no-deadlock (ADR-0009).

The bus is the F1 backbone; ADR-0009 flags deadlock/backpressure when bridging
background-thread callbacks as *the* risk. These tests exercise exactly that.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.core.api.events import EventBus


class Ping:
    def __init__(self, n: int) -> None:
        self.n = n


class Pong:
    pass


def test_drain_delivers_to_matching_subscriber() -> None:
    bus = EventBus()
    got: list[int] = []
    bus.subscribe(Ping, lambda e: got.append(e.n))
    bus.publish(Ping(1))
    bus.publish(Ping(2))
    assert bus.drain() == 2
    assert got == [1, 2]


def test_type_filtering_and_wildcard() -> None:
    bus = EventBus()
    pings: list[object] = []
    all_events: list[object] = []
    bus.subscribe(Ping, pings.append)
    bus.subscribe(None, all_events.append)  # wildcard
    bus.publish(Ping(1))
    bus.publish(Pong())
    bus.drain()
    assert len(pings) == 1
    assert len(all_events) == 2


def test_subclass_matching() -> None:
    class Base:
        pass

    class Derived(Base):
        pass

    bus = EventBus()
    seen: list[object] = []
    bus.subscribe(Base, seen.append)
    bus.publish(Derived())
    bus.drain()
    assert len(seen) == 1


def test_cancel_stops_delivery() -> None:
    bus = EventBus()
    got: list[object] = []
    sub = bus.subscribe(Ping, got.append)
    bus.publish(Ping(1))
    bus.drain()
    sub.cancel()
    bus.publish(Ping(2))
    bus.drain()
    assert len(got) == 1


def test_bad_subscriber_does_not_kill_bus() -> None:
    bus = EventBus()
    good: list[object] = []

    def boom(_e: object) -> None:
        raise RuntimeError("subscriber blew up")

    bus.subscribe(Ping, boom)
    bus.subscribe(Ping, good.append)
    bus.publish(Ping(1))
    bus.drain()
    assert len(good) == 1  # the good subscriber still ran


def test_backpressure_drops_oldest_never_blocks() -> None:
    bus = EventBus(maxsize=4)
    # Publish far more than capacity from the "producer" without a dispatcher
    # running — publish must never block, it drops the oldest instead.
    for i in range(100):
        bus.publish(Ping(i))
    assert bus.dropped >= 96
    delivered: list[int] = []
    bus.subscribe(Ping, lambda e: delivered.append(e.n))
    bus.drain()
    # Only the most recent survive; the newest event is always kept.
    assert delivered  # something survived
    assert delivered[-1] == 99


def test_dispatcher_thread_delivers() -> None:
    bus = EventBus()
    done = threading.Event()
    got: list[int] = []

    def on_ping(e: Ping) -> None:
        got.append(e.n)
        if e.n == 9:
            done.set()

    bus.subscribe(Ping, on_ping)
    bus.start()
    try:
        for i in range(10):
            bus.publish(Ping(i))
        assert done.wait(timeout=3.0), "dispatcher did not deliver in time"
    finally:
        bus.stop()
    assert got == list(range(10))


def test_concurrent_publishers_no_deadlock() -> None:
    """The core case: many background threads publish while the dispatcher runs.

    A subscriber that itself publishes must not deadlock (subscribers run
    outside the registry lock).
    """
    bus = EventBus(maxsize=8192)
    received = []
    lock = threading.Lock()

    def on_ping(e: Ping) -> None:
        with lock:
            received.append(e.n)

    bus.subscribe(Ping, on_ping)
    bus.start()

    def worker(base: int) -> None:
        for i in range(200):
            bus.publish(Ping(base + i))

    threads = [threading.Thread(target=worker, args=(t * 1000,)) for t in range(8)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive(), "publisher thread hung — possible deadlock"
        # Give the dispatcher a moment to drain the backlog.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            with lock:
                if len(received) == 1600:
                    break
            time.sleep(0.02)
    finally:
        bus.stop()
    with lock:
        # No drops expected: queue was sized above the total volume.
        assert len(received) == 1600, f"got {len(received)} of 1600 (dropped={bus.dropped})"


def test_subscriber_can_publish_from_within_dispatch() -> None:
    bus = EventBus()
    pongs: list[object] = []
    bus.subscribe(Ping, lambda _e: bus.publish(Pong()))
    bus.subscribe(Pong, pongs.append)
    bus.publish(Ping(1))
    # First drain dispatches Ping (which enqueues Pong); second drain the Pong.
    bus.drain()
    bus.drain()
    assert len(pongs) == 1


def test_stop_is_idempotent_and_safe_without_start() -> None:
    bus = EventBus()
    bus.stop()  # never started — must not raise
    bus.start()
    bus.start()  # idempotent
    bus.stop()
    bus.stop()  # idempotent
