"""
bench_scenario.py — Track R2 M0 bench harness core driver.

Builds N real ``MonitorWorker`` instances (FFmpegRecorderAdapter +
RecorderSupervisor + BufferManager, the exact wiring ``runtime/backend.py``
uses in production) directly — no IPC, no Tauri, no role/UI layer — and runs a
fixed scenario against them: steady state, injected crashes, an injected
stall, a churn loop (rapid stop/start with kills to probe the orphan race),
and an optional hard-kill self-test (Job Object reaping without Python
cleanup).  Emits a JSON summary consumed by ``bench_report.py``.

Reads the exact same env vars as the real app (``CAPTURE_PIPELINE``,
``SEGMENT_DURATION``, ``TELEMETRY_CSV``, ...) via ``app.infrastructure.config``
— set them before invoking this script (``bench_recording.ps1`` does this).

Usage::

    python -m tools.bench_scenario run --monitors 2 --duration-s 60 \\
        --crashes 1 --churn 5 --out results.json

    python -m tools.bench_scenario hard-kill-test --out hardkill.json
    python -m tools.bench_scenario check-orphans --pidfile hardkill.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# PYTHONPATH=project convention (see project/tests) — make `app.*` importable
# when this script is invoked directly rather than via -m from project/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil  # noqa: E402

from app.adapters.filesystem.storage_adapter import FilesystemStorageAdapter  # noqa: E402
from app.adapters.ffmpeg.hourly_recording_builder import HourlyRecordingBuilder  # noqa: E402
from app.adapters.ffmpeg.recorder_adapter import _STALL_GRACE_SECONDS  # noqa: E402
from app.adapters.monitor.screeninfo_adapter import ScreeninfoMonitorAdapter  # noqa: E402
from app.core.recording_service.models import MonitorInfo  # noqa: E402
from app.infrastructure.config import get_settings  # noqa: E402
from app.infrastructure.proc_telemetry import configure_telemetry, get_telemetry  # noqa: E402
from app.runtime.backend import build_worker  # noqa: E402


def _synthesize_monitors(count: int) -> list[MonitorInfo]:
    """Real detected monitors, tiled/synthesized up to *count* if fewer are attached.

    Synthetic entries capture a real (possibly overlapping) desktop region —
    they exist to exercise subprocess/thread governance at N-scale on a dev
    box with fewer physical displays, not to validate captured pixel content.
    """
    real = ScreeninfoMonitorAdapter().list_monitors()
    if len(real) >= count:
        return real[:count]
    monitors = list(real)
    base = real[0] if real else MonitorInfo(name="Synthetic", width=1920, height=1080, x=0, y=0, is_primary=True, index=0)
    while len(monitors) < count:
        i = len(monitors)
        monitors.append(
            MonitorInfo(
                name=f"Synthetic-{i}",
                width=640,
                height=360,
                x=base.x + (i * 80) % max(1, base.width - 640),
                y=base.y + (i * 60) % max(1, base.height - 360),
                is_primary=False,
                index=i,
            )
        )
    return monitors


def _ffmpeg_children_of(pid: int) -> list[int]:
    try:
        me = psutil.Process(pid)
    except psutil.Error:
        return []
    return [c.pid for c in me.children(recursive=True) if "ffmpeg" in c.name().lower()]


def _wait_for(predicate, timeout_s: float, poll_s: float = 0.1) -> float:
    """Poll *predicate* until True; return elapsed seconds, or -1.0 on timeout."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if predicate():
            return time.monotonic() - start
        time.sleep(poll_s)
    return -1.0


class BenchScenario:
    def __init__(self, monitors: int, segment_duration: int, out: Path):
        # NOTE: Settings reads os.getenv() at class-body (import) time, which has
        # already run by the time __init__ executes — setting SEGMENT_DURATION here
        # would be a no-op. bench_recording.ps1 sets $env:SEGMENT_DURATION before
        # launching this process; the `segment_duration` param is only used to
        # cross-check against what Settings actually resolved (see the assert below).
        self.settings = get_settings()
        if self.settings.segment_duration != segment_duration:
            print(
                f"[bench] WARNING: requested segment_duration={segment_duration}s but "
                f"Settings resolved {self.settings.segment_duration}s — set $env:SEGMENT_DURATION "
                "before launching this process (bench_recording.ps1 does this).",
                flush=True,
            )
        self.storage = FilesystemStorageAdapter()
        self.out = out
        self.metrics: dict = {
            "pipeline": self.settings.capture_pipeline,
            "monitors_requested": monitors,
            "segment_duration": self.settings.segment_duration,
            "events": [],
        }
        configure_telemetry(self.settings.proc_telemetry_interval_seconds)
        get_telemetry().start()

        monitor_infos = _synthesize_monitors(monitors)
        raw_clips_dir = self.settings.segment_dir.parent / "bench_raw_clips"
        self.workers = []
        for m in monitor_infos:
            builder = HourlyRecordingBuilder(
                output_dir=raw_clips_dir,
                monitor_count=1,
                monitor_index=m.index,
                window_minutes=self.settings.clip_window_minutes,
                max_size_mb=self.settings.clip_max_size_mb,
                on_clip_ready=lambda *_a, **_k: None,
                codec=self.settings.video_codec,
            )
            worker = build_worker(m, self.storage, self.settings, builder)
            self.workers.append(worker)

    def _log_event(self, kind: str, **fields) -> None:
        entry = {"kind": kind, "ts": time.time(), **fields}
        self.metrics["events"].append(entry)
        print(f"[bench] {kind}: {fields}", flush=True)

    def start_all(self) -> None:
        # MonitorWorker.start() already starts its own supervisor internally.
        for w in self.workers:
            w.start()
        self._log_event("all_started", count=len(self.workers))

    def stop_all(self) -> None:
        # MonitorWorker.stop() already stops its own supervisor internally.
        for w in self.workers:
            w.stop()
        self._log_event("all_stopped")

    def steady_state(self, duration_s: float) -> None:
        self._log_event("steady_state_begin", duration_s=duration_s)
        time.sleep(duration_s)
        self._log_event("steady_state_end")

    def inject_crash(self, worker_index: int = 0) -> None:
        """Kill the FFmpeg child directly (bypassing .stop()) and measure MTTR."""
        worker = self.workers[worker_index]
        recorder = worker._recorder  # noqa: SLF001 — bench harness, not production code
        proc = recorder._process  # noqa: SLF001
        if proc is None:
            self._log_event("crash_skipped", reason="no_process", worker=worker_index)
            return
        old_pid = proc.pid
        try:
            psutil.Process(old_pid).kill()
        except psutil.Error:
            pass
        elapsed = _wait_for(
            lambda: recorder.is_running() and recorder._process is not None  # noqa: SLF001
            and recorder._process.pid != old_pid,
            timeout_s=45.0,
        )
        mttr = elapsed if elapsed >= 0 else None
        self._log_event("crash_injected", worker=worker_index, old_pid=old_pid, mttr_s=mttr)

    def inject_stall(self, worker_index: int = 0, timeout_s: Optional[float] = None) -> None:
        """Suspend the FFmpeg child (no new frames) and measure stall-detection MTTR.

        Default timeout is derived from the ACTIVE segment_duration + the
        watchdog's stall grace (recorder_adapter._STALL_GRACE_SECONDS=60) plus
        a safety margin — with production defaults (SEGMENT_DURATION=300) the
        real detection threshold is 360s; a fixed short timeout would always
        time out (returning mttr_s=None) without ever seeing a real number.
        """
        if timeout_s is None:
            timeout_s = self.settings.segment_duration + _STALL_GRACE_SECONDS + 30
        worker = self.workers[worker_index]
        recorder = worker._recorder  # noqa: SLF001
        proc = recorder._process  # noqa: SLF001
        if proc is None:
            self._log_event("stall_skipped", reason="no_process", worker=worker_index)
            return
        old_pid = proc.pid
        try:
            psutil.Process(old_pid).suspend()
        except psutil.Error:
            self._log_event("stall_skipped", reason="suspend_failed", worker=worker_index)
            return
        t0 = time.monotonic()
        elapsed = _wait_for(
            lambda: recorder._process is None or recorder._process.pid != old_pid,  # noqa: SLF001
            timeout_s=timeout_s,
        )
        # If detection never fired, resume the suspended process ourselves so
        # it doesn't leak as a permanently-frozen orphan for the rest of the run.
        try:
            psutil.Process(old_pid).resume()
        except psutil.Error:
            pass
        mttr = elapsed if elapsed >= 0 else None
        self._log_event("stall_injected", worker=worker_index, old_pid=old_pid, mttr_s=mttr)

    def churn(self, cycles: int, worker_index: int = 0, kill_race_ms: float = 20.0) -> dict:
        """Rapid stop()/start() cycles with a kill injected just after each
        start — probes the documented Popen→assign-to-Job race window
        (recorder_adapter.py / process_guard.py / supervisor.py). Returns
        orphan accounting.
        """
        worker = self.workers[worker_index]
        me_pid = os.getpid()
        pre_orphans = set(_ffmpeg_children_of(me_pid))
        killed = 0
        for _ in range(cycles):
            worker.stop()
            try:
                worker.start()
            except RuntimeError:
                pass
            time.sleep(kill_race_ms / 1000.0)
            recorder = worker._recorder  # noqa: SLF001
            proc = recorder._process  # noqa: SLF001
            if proc is not None:
                try:
                    psutil.Process(proc.pid).kill()
                    killed += 1
                except psutil.Error:
                    pass
            time.sleep(0.3)  # let the supervisor's crash notification land
        # settle: allow the last restart to complete
        time.sleep(2.0)
        post_orphans = set(_ffmpeg_children_of(me_pid)) - pre_orphans
        # "orphan" here = an ffmpeg.exe child process no longer tracked by any
        # live recorder in this run (the current recorder's own PID excluded).
        live_pids = {w._recorder._process.pid for w in self.workers if w._recorder._process is not None}  # noqa: SLF001
        candidates = [p for p in post_orphans if p not in live_pids]
        # A batch clip-build (HourlyRecordingBuilder -> run_batched_ffmpeg) can
        # legitimately still be running at this exact instant — it's tracked
        # under category="batch", not the recorder Job, so it shows up as an
        # "extra" ffmpeg.exe child without being an orphan at all. Re-check
        # after a grace period: a real orphan stays alive; a batch build
        # finishes (these are small test clips — seconds, not minutes).
        if candidates:
            time.sleep(10.0)
            orphans = [p for p in candidates if psutil.pid_exists(p)]
        else:
            orphans = []
        result = {"cycles": cycles, "killed": killed, "orphans": len(orphans), "orphan_pids": orphans}
        self._log_event("churn_complete", **result)
        return result

    def write(self) -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_text(json.dumps(self.metrics, indent=2), encoding="utf-8")
        print(f"[bench] wrote {self.out}", flush=True)


def _cmd_run(args: argparse.Namespace) -> None:
    scenario = BenchScenario(
        monitors=args.monitors, segment_duration=args.segment_duration, out=Path(args.out)
    )
    try:
        scenario.start_all()
        scenario.steady_state(args.duration_s)
        for i in range(args.crashes):
            scenario.inject_crash(worker_index=0)
            time.sleep(2.0)
        if args.stall:
            scenario.inject_stall(worker_index=0)
        if args.churn > 0:
            scenario.churn(cycles=args.churn, worker_index=min(1, len(scenario.workers) - 1))
    finally:
        scenario.stop_all()
        get_telemetry().stop()
        scenario.write()


def _cmd_hard_kill_test(args: argparse.Namespace) -> None:
    """Spawn one worker, record its FFmpeg child PID(s), then os._exit(1) —
    no atexit, no finally — to prove the Job Object (not Python cleanup) is
    what reaps the child when the owning process dies abruptly.
    """
    scenario = BenchScenario(monitors=1, segment_duration=args.segment_duration, out=Path(args.out))
    scenario.start_all()
    _wait_for(lambda: scenario.workers[0]._recorder._process is not None, timeout_s=15.0)  # noqa: SLF001
    ffmpeg_pids = _ffmpeg_children_of(os.getpid())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"parent_pid": os.getpid(), "ffmpeg_pids": ffmpeg_pids, "ts": time.time()}),
        encoding="utf-8",
    )
    print(f"[bench] hard-kill-test armed: parent={os.getpid()} ffmpeg={ffmpeg_pids}", flush=True)
    sys.stdout.flush()
    os._exit(1)  # abrupt — deliberately skips stop()/atexit to simulate a real crash


def _cmd_check_orphans(args: argparse.Namespace) -> None:
    data = json.loads(Path(args.pidfile).read_text(encoding="utf-8"))
    alive = []
    for pid in data["ffmpeg_pids"]:
        if psutil.pid_exists(pid):
            try:
                if "ffmpeg" in psutil.Process(pid).name().lower():
                    alive.append(pid)
            except psutil.Error:
                pass
    result = {"parent_pid": data["parent_pid"], "ffmpeg_pids": data["ffmpeg_pids"], "orphaned": alive}
    print(json.dumps(result, indent=2))
    if alive:
        for pid in alive:
            try:
                psutil.Process(pid).kill()
            except psutil.Error:
                pass
        print(f"[bench] WARNING: {len(alive)} orphaned ffmpeg process(es) found and killed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track R2 M0 bench scenario driver")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="steady-state + crash/stall/churn scenario")
    p_run.add_argument("--monitors", type=int, default=1)
    p_run.add_argument("--duration-s", type=float, default=60.0)
    p_run.add_argument("--crashes", type=int, default=1)
    p_run.add_argument("--stall", action="store_true")
    p_run.add_argument("--churn", type=int, default=5)
    p_run.add_argument("--segment-duration", type=int, default=5)
    p_run.add_argument("--out", default="bench_results.json")
    p_run.set_defaults(func=_cmd_run)

    p_hk = sub.add_parser("hard-kill-test", help="arm+self-terminate for the orphan/Job-Object test")
    p_hk.add_argument("--segment-duration", type=int, default=5)
    p_hk.add_argument("--out", default="hardkill_state.json")
    p_hk.set_defaults(func=_cmd_hard_kill_test)

    p_co = sub.add_parser("check-orphans", help="verify no ffmpeg survives the hard-kill-test parent")
    p_co.add_argument("--pidfile", required=True)
    p_co.set_defaults(func=_cmd_check_orphans)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
