"""
spike_m2a_ctypes_guard.py -- Track R2 M2a spike (DISCARDABLE, not shipped).

Question this answers: does the FFmpeg-orphan race actually need a Rust crate
(M2's original justification: "std::Command doesn't expose the thread
handle"), or does pure ctypes already close it -- given process_guard.py
already makes raw ctypes Win32 calls (OpenProcess, AssignProcessToJobObject)
in this exact codebase?

Mechanism: today's recorder_adapter.py does `subprocess.Popen(cmd)` (child
starts running immediately) THEN `assign_to_job(proc)` afterwards -- a real
gap where the owning Python process could die before the child is ever a Job
member, leaking it as a permanent orphan (the race documented in
monitor_worker.py:82-85 / supervisor.py:159-170). `subprocess.Popen` cannot
close this gap: even with `creationflags=CREATE_SUSPENDED` it never exposes
the new thread's handle, so nothing can call ResumeThread after assigning the
Job. `CreateProcessW` (called directly via ctypes, bypassing `subprocess`
entirely) returns both handles in its PROCESS_INFORMATION out-param --
letting us: create suspended -> assign to Job -> ResumeThread, with no window
where the child can run (spawn further children, exit, or otherwise escape)
before Job membership is in effect.

Usage::

    python spike_m2a_ctypes_guard.py race --cycles 500
    python spike_m2a_ctypes_guard.py hard-kill-arm --out state.json
    python spike_m2a_ctypes_guard.py hard-kill-check --pidfile state.json
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import random
import sys
import time
from pathlib import Path

import psutil

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
INFINITE = 0xFFFFFFFF

_JOBOBJECTINFOCLASS_ExtendedLimitInformation = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _BasicLimitInfo(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _ExtendedLimitInfo(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInfo),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
    wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
    ctypes.POINTER(_STARTUPINFOW), ctypes.POINTER(_PROCESS_INFORMATION),
]
_kernel32.CreateProcessW.restype = wintypes.BOOL
_kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
_kernel32.ResumeThread.restype = wintypes.DWORD
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.TerminateProcess.restype = wintypes.BOOL
_kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
_kernel32.CreateJobObjectW.restype = wintypes.HANDLE
_kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
_kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_kernel32.SetInformationJobObject.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD


class GuardedSpawnError(RuntimeError):
    pass


def spawn_guarded_suspended(cmdline: str) -> tuple[int, int, int, int]:
    """CreateProcessW(CREATE_SUSPENDED) -> new Job w/ KILL_ON_JOB_CLOSE ->
    AssignProcessToJobObject -> ResumeThread.

    Returns (pid, hProcess, hThread, hJob). No window exists where the child
    can execute (spawn descendants, exit, or otherwise escape) before it is a
    Job member -- this is the structural fix M2 assigned to Rust.
    """
    startup_info = _STARTUPINFOW()
    startup_info.cb = ctypes.sizeof(_STARTUPINFOW)
    proc_info = _PROCESS_INFORMATION()
    buf = ctypes.create_unicode_buffer(cmdline)

    ok = _kernel32.CreateProcessW(
        None, buf, None, None, False,
        CREATE_SUSPENDED | CREATE_NO_WINDOW, None, None,
        ctypes.byref(startup_info), ctypes.byref(proc_info),
    )
    if not ok:
        raise GuardedSpawnError(f"CreateProcessW failed: {ctypes.WinError(ctypes.get_last_error())}")

    h_process, h_thread, pid = proc_info.hProcess, proc_info.hThread, proc_info.dwProcessId
    try:
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            raise GuardedSpawnError(f"CreateJobObjectW failed: {ctypes.WinError(ctypes.get_last_error())}")
        info = _ExtendedLimitInfo()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            job, _JOBOBJECTINFOCLASS_ExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        ):
            _kernel32.CloseHandle(job)
            raise GuardedSpawnError(f"SetInformationJobObject failed: {ctypes.WinError(ctypes.get_last_error())}")

        if not _kernel32.AssignProcessToJobObject(job, h_process):
            err = ctypes.WinError(ctypes.get_last_error())
            _kernel32.CloseHandle(job)
            raise GuardedSpawnError(f"AssignProcessToJobObject failed (still suspended): {err}")

        # Still suspended here -- Job membership is now guaranteed BEFORE any
        # code in the child can run. This is the entire structural fix.
        if _kernel32.ResumeThread(h_thread) == 0xFFFFFFFF:
            raise GuardedSpawnError(f"ResumeThread failed: {ctypes.WinError(ctypes.get_last_error())}")
    except GuardedSpawnError:
        _kernel32.TerminateProcess(h_process, 1)
        _kernel32.CloseHandle(h_process)
        _kernel32.CloseHandle(h_thread)
        raise

    return pid, h_process, h_thread, job


def race_test(cycles: int) -> dict:
    """Spawn+race-kill *cycles* times; a child is 'orphaned' if it survives
    past its owning handles being closed (i.e. psutil still sees the pid
    alive well after we killed it and closed everything)."""
    me = psutil.Process(os.getpid())
    pre_children = {c.pid for c in me.children(recursive=True)}
    failures: list[str] = []
    survivors: list[int] = []
    resume_failures = 0

    for i in range(cycles):
        cmdline = f'"{sys.executable}" -c "import time; time.sleep(2)"'
        try:
            pid, h_process, h_thread, job = spawn_guarded_suspended(cmdline)
        except GuardedSpawnError as exc:
            failures.append(f"cycle {i}: spawn failed: {exc}")
            continue

        # Race: kill at a random point very close to spawn -- before this
        # prototype existed, this window was exactly where subprocess.Popen's
        # separately-called assign_to_job() could lose the race.
        time.sleep(random.uniform(0, 0.01))
        _kernel32.TerminateProcess(h_process, 1)
        _kernel32.WaitForSingleObject(h_process, 2000)
        _kernel32.CloseHandle(h_thread)
        _kernel32.CloseHandle(h_process)
        _kernel32.CloseHandle(job)

        time.sleep(0.02)
        if psutil.pid_exists(pid):
            try:
                if "python" in psutil.Process(pid).name().lower():
                    survivors.append(pid)
            except psutil.Error:
                pass

    time.sleep(0.5)
    post_children = {c.pid for c in me.children(recursive=True)} - pre_children
    leaked = [p for p in post_children if psutil.pid_exists(p)]

    result = {
        "cycles": cycles,
        "spawn_failures": len(failures),
        "failure_details": failures[:10],
        "survivors_immediately_after_kill": survivors,
        "leaked_children_at_end": leaked,
        "orphans": len(survivors) + len(leaked),
    }
    return result


def _cmd_race(args: argparse.Namespace) -> None:
    result = race_test(args.cycles)
    print(json.dumps(result, indent=2))
    verdict = "PASS (0 orphans)" if result["orphans"] == 0 else f"FAIL ({result['orphans']} orphans)"
    print(f"\n[m2a spike] race test x{args.cycles}: {verdict}")


def _cmd_hard_kill_arm(args: argparse.Namespace) -> None:
    """Spawn one long-lived guarded child, record it, then os._exit(1) --
    proves the Job's KILL_ON_JOB_CLOSE (not this process's cleanup) reaps it.
    """
    cmdline = f'"{sys.executable}" -c "import time; time.sleep(30)"'
    pid, h_process, h_thread, job = spawn_guarded_suspended(cmdline)
    _kernel32.CloseHandle(h_thread)
    Path(args.out).write_text(json.dumps({"pid": pid, "ts": time.time()}), encoding="utf-8")
    print(f"[m2a spike] armed: child pid={pid}, self-terminating now (os._exit)")
    sys.stdout.flush()
    os._exit(1)


def _cmd_hard_kill_check(args: argparse.Namespace) -> None:
    data = json.loads(Path(args.pidfile).read_text(encoding="utf-8"))
    pid = data["pid"]
    alive = psutil.pid_exists(pid)
    print(json.dumps({"pid": pid, "orphaned": alive}, indent=2))
    if alive:
        try:
            psutil.Process(pid).kill()
        except psutil.Error:
            pass
        print(f"[m2a spike] FAIL: pid {pid} survived the parent's abrupt death (os._exit).")
    else:
        print(f"[m2a spike] PASS: pid {pid} was reaped by the Job (KILL_ON_JOB_CLOSE) with zero Python cleanup.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track R2 M2a ctypes-vs-Rust spike (discardable)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_race = sub.add_parser("race", help="x-cycle spawn+kill race test")
    p_race.add_argument("--cycles", type=int, default=500)
    p_race.set_defaults(func=_cmd_race)

    p_arm = sub.add_parser("hard-kill-arm", help="arm+self-terminate for the Job-Object reap test")
    p_arm.add_argument("--out", default="m2a_hardkill_state.json")
    p_arm.set_defaults(func=_cmd_hard_kill_arm)

    p_check = sub.add_parser("hard-kill-check", help="verify the armed child was reaped")
    p_check.add_argument("--pidfile", required=True)
    p_check.set_defaults(func=_cmd_hard_kill_check)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
