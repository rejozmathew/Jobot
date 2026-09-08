"""Tests for job_applier.workspace_process."""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from job_applier.workspace_process import (
    FileLock,
    OwnedProcess,
    ProtocolError,
    check_breakaway_permitted,
    detached_launch,
    process_identity,
    process_matches,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SUBPROCESS_ENV = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    from job_applier.workspace_process import kernel32
    SYNCHRONIZE = 0x00100000
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    WAIT_TIMEOUT = 0x00000102

    def is_pid_alive(pid: int) -> bool:
        if not pid or pid <= 0:
            return False
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not h:
            return False
        try:
            return kernel32.WaitForSingleObject(h, 0) == WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(h)

    def terminate_and_wait(pid: int, timeout_s: float = 3.0) -> None:
        if not is_pid_alive(pid):
            return
        h = kernel32.OpenProcess(0x0001 | SYNCHRONIZE, False, pid)
        if h:
            try:
                kernel32.TerminateProcess(h, 1)
                kernel32.WaitForSingleObject(h, int(timeout_s * 1000))
            finally:
                kernel32.CloseHandle(h)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not is_pid_alive(pid):
                return
            time.sleep(0.05)
else:
    def is_pid_alive(pid: int) -> bool:
        if not pid or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def terminate_and_wait(pid: int, timeout_s: float = 3.0) -> None:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not is_pid_alive(pid):
                return
            time.sleep(0.05)


# -----------------------------------------------------------------------------
# Test 1: Lock exclusion across threads and processes
# -----------------------------------------------------------------------------

def test_lock_exclusion_across_threads_and_processes(tmp_path):
    lock_file = tmp_path / "test.lock"
    lock1 = FileLock(lock_file)
    lock1.acquire()

    # Verify is_locked reports True
    assert FileLock.is_locked(lock_file) is True

    # 1. Thread exclusion in same process
    thread_result = []

    def try_thread_acquire():
        l = FileLock(lock_file)
        try:
            l.acquire()
            thread_result.append("acquired")
        except ProtocolError as exc:
            thread_result.append(exc.code)

    t = threading.Thread(target=try_thread_acquire)
    t.start()
    t.join(timeout=5)
    assert thread_result == ["local_lock_busy"]

    # 2. Process exclusion across separate OS processes
    code = f"""
import sys
from job_applier.workspace_process import FileLock, ProtocolError
l = FileLock(r"{lock_file}")
try:
    l.acquire()
    print("ACQUIRED")
except ProtocolError as exc:
    print(exc.code)
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=SUBPROCESS_ENV,
    )
    assert proc.stdout.strip() == "local_lock_busy"

    # Release lock
    lock1.release()

    # Verify is_locked reports False and lock file remains on disk
    assert FileLock.is_locked(lock_file) is False
    assert lock_file.exists(), "Lock file must remain on disk after release"

    # Now another process can acquire it successfully
    proc2 = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=SUBPROCESS_ENV,
    )
    assert proc2.stdout.strip() == "ACQUIRED"

    # Context manager works and releases cleanly
    with FileLock(lock_file):
        assert FileLock.is_locked(lock_file) is True
    assert FileLock.is_locked(lock_file) is False


# -----------------------------------------------------------------------------
# Test 2: Stale PID identity rejection
# -----------------------------------------------------------------------------

def test_stale_pid_identity_rejection():
    # Launch a very short-lived process
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    ident = process_identity(proc.pid)
    proc.wait(timeout=5)

    # Process is now terminated
    assert is_pid_alive(proc.pid) is False

    # 1. Stale / dead process identity rejected
    if ident is not None:
        assert process_matches(ident) is False
    assert process_identity(proc.pid) is None

    # 2. Forged creation time rejected even if PID matches a running process
    curr_pid = os.getpid()
    curr_ident = process_identity(curr_pid)
    assert curr_ident is not None
    assert process_matches(curr_ident) is True

    fake_ident = {"pid": curr_pid, "created": curr_ident["created"] + 9999999}
    assert process_matches(fake_ident) is False, "Must reject matching PID with wrong creation timestamp"

    # 3. Non-existent PID and bad inputs rejected
    assert process_matches({"pid": 99999999, "created": 12345}) is False
    assert process_matches(None) is False
    assert process_matches({}) is False
    assert process_identity(-1) is None


# -----------------------------------------------------------------------------
# Test 3: Owned child & grandchild termination when host is forcibly killed
# -----------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object tests require Windows")
def test_owned_child_and_grandchild_termination_when_host_killed():
    # Local synthetic artifacts directory
    artifacts_dir = REPO_ROOT / "artifacts" / "jobbot-v1-private" / "runtime-process-tests"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    uid_tag = f"{os.getpid()}_{int(time.time() * 1000)}"
    status_file = artifacts_dir / f"test_kill_status_{uid_tag}.json"
    child_script = artifacts_dir / f"test_child_{uid_tag}.py"
    host_script = artifacts_dir / f"test_host_{uid_tag}.py"

    # Child script creates grandchild, writes both PIDs to status_file, then sleeps
    child_script.write_text(
        """import json, os, subprocess, sys, time
gc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
status = {"child_pid": os.getpid(), "grandchild_pid": gc.pid}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(status, f)
time.sleep(60)
""",
        encoding="utf-8",
    )

    # Host script launches child script using OwnedProcess, waits for status file, prints HOST_READY, sleeps
    host_script.write_text(
        """import json, os, sys, time
from job_applier.workspace_process import OwnedProcess

status_path = sys.argv[1]
child_path = sys.argv[2]

owned = OwnedProcess.launch([sys.executable, child_path, status_path])
for _ in range(100):
    if os.path.exists(status_path):
        break
    time.sleep(0.05)

print("HOST_READY", flush=True)
time.sleep(60)
""",
        encoding="utf-8",
    )

    host_proc = subprocess.Popen(
        [sys.executable, str(host_script), str(status_file), str(child_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
        env=SUBPROCESS_ENV,
    )

    child_pid = None
    grandchild_pid = None

    try:
        # Wait for host to signal ready and status file to be written
        line = host_proc.stdout.readline()
        assert "HOST_READY" in line, f"Host output unexpected: {line}, stderr: {host_proc.stderr.read()}"

        with open(status_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        child_pid = data["child_pid"]
        grandchild_pid = data["grandchild_pid"]

        # Verify child and grandchild are actively running
        assert is_pid_alive(child_pid) is True, "Child must be alive before host kill"
        assert is_pid_alive(grandchild_pid) is True, "Grandchild must be alive before host kill"

        # Forcibly terminate host process (simulating host crash)
        host_proc.kill()
        host_proc.wait(timeout=5)

        # Poll for OS to terminate Job Object descendants
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if not is_pid_alive(child_pid) and not is_pid_alive(grandchild_pid):
                break
            time.sleep(0.1)

        # Assert BOTH child and grandchild were terminated by Windows Job Object
        assert is_pid_alive(child_pid) is False, "Child process must be terminated when host dies"
        assert is_pid_alive(grandchild_pid) is False, "Grandchild process must be terminated when host dies"

    finally:
        # Guarantee all synthetic children are stopped
        for pid in (child_pid, grandchild_pid):
            if pid:
                terminate_and_wait(pid)
        try:
            host_proc.kill()
        except Exception:
            pass
        for p in (status_file, child_script, host_script):
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass


# -----------------------------------------------------------------------------
# Test 4: OwnedProcess normal stop kills owned job and waits for child
# -----------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object tests require Windows")
def test_owned_process_stop_and_alive(tmp_path):
    out_file = tmp_path / "child_out.log"
    owned = OwnedProcess.launch(
        [sys.executable, "-c", "import time; print('hello'); time.sleep(10)"],
        stdout_path=out_file,
    )
    try:
        assert owned.alive() is True
        assert owned.pid > 0
        assert process_matches(owned.identity) is True
    finally:
        owned.stop(timeout=5)

    assert owned.alive() is False
    assert is_pid_alive(owned.pid) is False
    assert out_file.exists()


# -----------------------------------------------------------------------------
# Test 5: Detached launch breakaway denial handling
# -----------------------------------------------------------------------------

def test_detached_launch_breakaway_denial_behavior():
    permitted, reason = check_breakaway_permitted()
    if not permitted:
        # In a Job Object that denies breakaway, detached_launch MUST raise ProtocolError('breakaway_denied')
        with pytest.raises(ProtocolError) as exc_info:
            detached_launch([sys.executable, "-c", "pass"])
        assert exc_info.value.code == "breakaway_denied"
        assert "breakaway" in str(exc_info.value).lower()
    else:
        # Breakaway is permitted
        ident = detached_launch([sys.executable, "-c", "pass"])
        assert isinstance(ident, dict)
        assert ident["pid"] > 0


# -----------------------------------------------------------------------------
# Test 6: Actual Windows short-lived shell exit while detached host remains alive
# -----------------------------------------------------------------------------

def test_detached_host_survives_short_lived_shell_exit():
    permitted, reason = check_breakaway_permitted()
    if not permitted:pytest.skip(reason)
    artifacts_dir = REPO_ROOT / "artifacts" / "jobbot-v1-private" / "runtime-process-tests"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    uid_tag = f"{os.getpid()}_{int(time.time() * 1000)}"
    out_file = artifacts_dir / f"detached_out_{uid_tag}.log"
    shell_script = artifacts_dir / f"short_lived_shell_{uid_tag}.py"

    # Short-lived shell script: launches detached host, writes identity, and exits immediately
    shell_code = f"""
import json
import sys
from job_applier.workspace_process import detached_launch

# Host will sleep for 20 seconds
host_cmd = [sys._base_executable, "-c", "import time; print('HOST_ALIVE', flush=True); time.sleep(20)"]
ident = detached_launch(host_cmd, stdout_path=r"{out_file}")
print(json.dumps(ident), flush=True)
sys.exit(0)
"""
    shell_script.write_text(shell_code, encoding="utf-8")

    # Run the short-lived shell process synchronously to completion
    res = subprocess.run(
        [sys.executable, str(shell_script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=SUBPROCESS_ENV,
    )
    assert res.returncode == 0, f"Shell failed: {res.stderr}"

    host_ident = json.loads(res.stdout.strip())
    host_pid = host_ident["pid"]

    try:
        # Short-lived shell has EXITED. Verify host process is STILL ALIVE and matches identity!
        assert is_pid_alive(host_pid) is True, "Detached host must survive shell exit"
        assert process_matches(host_ident) is True, "Process identity must match running detached host"

        # Wait briefly for host output to be flushed
        deadline = time.time() + 3.0
        found = False
        while time.time() < deadline:
            if out_file.exists() and "HOST_ALIVE" in out_file.read_text(encoding="utf-8"):
                found = True
                break
            time.sleep(0.1)
        assert found, f"Expected HOST_ALIVE in {out_file}"

    finally:
        # Guaranteed cleanup: stop all synthetic children launched
        terminate_and_wait(host_pid)
        assert is_pid_alive(host_pid) is False

        # Clean up temporary test artifacts
        if shell_script.exists():
            shell_script.unlink()
        if out_file.exists():
            out_file.unlink()
