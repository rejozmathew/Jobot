"""Focused tests for Linux workspace portability, process lifecycle, and /proc inventory."""
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from job_applier.managed_shared import ProtocolError
from job_applier.workspace_linux import (
    cleanup_linux_socket,
    cmdline_matches_user_data_dir,
    create_linux_listener,
    extract_user_data_dir,
    linux_profile_in_use,
    parse_cmdline_args,
)
from job_applier.workspace_process import OwnedProcess, process_identity, process_matches

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SUBPROCESS_ENV = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}


# -----------------------------------------------------------------------------
# Pure Parser Tests (Windows and Linux Usable)
# -----------------------------------------------------------------------------

def test_parse_cmdline_args_null_separated():
    raw = b"/usr/bin/google-chrome\x00--user-data-dir=/home/user/.profile\x00--headless=new\x00"
    args = parse_cmdline_args(raw)
    assert args == [
        "/usr/bin/google-chrome",
        "--user-data-dir=/home/user/.profile",
        "--headless=new",
    ]


def test_parse_cmdline_args_space_separated_and_list():
    raw_str = "/usr/bin/chrome --user-data-dir=/tmp/test --headless"
    assert parse_cmdline_args(raw_str) == [
        "/usr/bin/chrome",
        "--user-data-dir=/tmp/test",
        "--headless",
    ]
    raw_list = ["chrome", "--user-data-dir=/tmp/test"]
    assert parse_cmdline_args(raw_list) == ["chrome", "--user-data-dir=/tmp/test"]


def test_extract_user_data_dir_variations():
    # Equals syntax
    assert extract_user_data_dir(["chrome", "--user-data-dir=/path/to/dir"]) == "/path/to/dir"
    # Space separated syntax
    assert extract_user_data_dir(["chrome", "--user-data-dir", "/path/to/dir"]) == "/path/to/dir"
    # Quoted equals syntax
    assert extract_user_data_dir(["chrome", '--user-data-dir="/path with spaces/dir"']) == "/path with spaces/dir"
    # Quoted space syntax
    assert extract_user_data_dir(["chrome", "--user-data-dir", "'/path with spaces/dir'"]) == "/path with spaces/dir"
    # Quoted shell/program text is not an actual argv option of this process.
    assert extract_user_data_dir(["sh", "-c", 'chrome --user-data-dir="/path/to/dir" --headless']) is None
    # Absent
    assert extract_user_data_dir(["chrome", "--headless", "about:blank"]) is None


def test_cmdline_matches_user_data_dir_exact(tmp_path):
    target = tmp_path / "workspace_profile"
    target.mkdir()

    # Exact match with null bytes
    cmdline_null = f"/usr/bin/chrome\x00--user-data-dir={target}\x00--headless\x00".encode()
    assert cmdline_matches_user_data_dir(cmdline_null, target) is True

    # Trailing slash variation resolves to same canonical directory
    cmdline_slash = f"/usr/bin/chrome\x00--user-data-dir={target}/\x00--headless\x00".encode()
    assert cmdline_matches_user_data_dir(cmdline_slash, target) is True

    # Space separated variation
    cmdline_spaced = [sys.executable, "--user-data-dir", str(target)]
    assert cmdline_matches_user_data_dir(cmdline_spaced, target) is True

    # Different directory must NOT match
    other = tmp_path / "other_profile"
    other.mkdir()
    cmdline_other = f"/usr/bin/chrome\x00--user-data-dir={other}\x00".encode()
    assert cmdline_matches_user_data_dir(cmdline_other, target) is False

    # Prefix extension must NOT match (e.g. /path/to/dir2 vs /path/to/dir)
    target_ext = str(target) + "-extension"
    cmdline_prefix = f"/usr/bin/chrome\x00--user-data-dir={target_ext}\x00".encode()
    assert cmdline_matches_user_data_dir(cmdline_prefix, target) is False

    # Subdirectory of profile must NOT match
    sub = target / "sub_dir"
    sub.mkdir()
    cmdline_sub = f"/usr/bin/chrome\x00--user-data-dir={sub}\x00".encode()
    assert cmdline_matches_user_data_dir(cmdline_sub, target) is False


def test_cmdline_matches_case_sensitivity():
    lower = "/tmp/my_profile_case_test"
    upper = "/tmp/MY_PROFILE_CASE_TEST"

    cmdline = f"/usr/bin/chrome\x00--user-data-dir={upper}\x00".encode()
    # Case sensitive (Linux semantics): lower does NOT match upper
    assert cmdline_matches_user_data_dir(cmdline, lower, case_sensitive=True) is False
    # Case insensitive: lower matches upper
    assert cmdline_matches_user_data_dir(cmdline, lower, case_sensitive=False) is True


# -----------------------------------------------------------------------------
# Synthetic /proc Inventory Tests (Windows and Linux Usable)
# -----------------------------------------------------------------------------

def test_linux_profile_in_use_synthetic_match(tmp_path):
    proc_dir = tmp_path / "proc"
    proc_dir.mkdir()

    target_profile = tmp_path / "target_profile"
    target_profile.mkdir()

    # Process 1234: matches target_profile
    p1 = proc_dir / "1234"
    p1.mkdir()
    (p1 / "cmdline").write_bytes(f"google-chrome\x00--user-data-dir={target_profile}\x00".encode())
    (p1 / "stat").write_text("1234 (chrome) S 1 1234 1234 0 -1 4194304 100 0 0 0 10 20 0 0 20 0 1 0 55555 1000\n")

    # Process 5678: unrelated process
    p2 = proc_dir / "5678"
    p2.mkdir()
    (p2 / "cmdline").write_bytes(b"bash\x00-i\x00")
    (p2 / "stat").write_text("5678 (bash) S 1 5678 5678 0 -1 4194304 100 0 0 0 10 20 0 0 20 0 1 0 66666 1000\n")

    found_pid = linux_profile_in_use({"user_data_dir": str(target_profile)}, proc_path=proc_dir)
    assert found_pid == 1234


def test_linux_profile_in_use_synthetic_no_match(tmp_path):
    proc_dir = tmp_path / "proc"
    proc_dir.mkdir()

    target_profile = tmp_path / "target_profile"
    target_profile.mkdir()

    other_profile = tmp_path / "other_profile"
    other_profile.mkdir()

    p1 = proc_dir / "999"
    p1.mkdir()
    (p1 / "cmdline").write_bytes(f"google-chrome\x00--user-data-dir={other_profile}\x00".encode())

    found_pid = linux_profile_in_use({"user_data_dir": str(target_profile)}, proc_path=proc_dir)
    assert found_pid is None


def test_linux_profile_in_use_handles_zombies_honestly(tmp_path):
    proc_dir = tmp_path / "proc"
    proc_dir.mkdir()

    target_profile = tmp_path / "target_profile"
    target_profile.mkdir()

    # Process 2222: matches profile but is a zombie ('Z' in stat)
    p = proc_dir / "2222"
    p.mkdir()
    (p / "cmdline").write_bytes(f"google-chrome\x00--user-data-dir={target_profile}\x00".encode())
    (p / "stat").write_text("2222 (chrome) Z 1 2222 2222 0 -1 4194304 0 0 0 0 0 0 0 0 20 0 1 0 77777 0\n")

    found_pid = linux_profile_in_use({"user_data_dir": str(target_profile)}, proc_path=proc_dir)
    assert found_pid is None, "Zombie processes must not report profile in use"


def test_linux_profile_in_use_handles_missing_and_permission_honestly(tmp_path):
    proc_dir = tmp_path / "proc"
    proc_dir.mkdir()

    target_profile = tmp_path / "target_profile"
    target_profile.mkdir()

    # Process 3333: empty/missing cmdline (kernel worker or exited)
    p1 = proc_dir / "3333"
    p1.mkdir()
    (p1 / "cmdline").write_bytes(b"")

    # Non-digit directory in /proc (like /proc/sys or /proc/net)
    sys_dir = proc_dir / "sys"
    sys_dir.mkdir()

    found_pid = linux_profile_in_use({"user_data_dir": str(target_profile)}, proc_path=proc_dir)
    assert found_pid is None


def test_linux_profile_in_use_missing_proc_raises_inventory_unavailable(tmp_path):
    nonexistent = tmp_path / "no_such_proc"
    with pytest.raises(ProtocolError) as exc_info:
        linux_profile_in_use({"user_data_dir": str(tmp_path)}, proc_path=nonexistent)
    assert exc_info.value.code == "workspace_process_inventory_unavailable"


# -----------------------------------------------------------------------------
# Linux-Specific Lifecycle and Host-Death Tests (Skipped on Windows)
# -----------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="Linux process group and socket tests require Linux")
def test_linux_socket_permissions_private(tmp_path):
    sock_path = str(tmp_path / "test.sock")
    listener = create_linux_listener(sock_path)
    try:
        mode = stat.S_IMODE(os.stat(sock_path).st_mode)
        # Permissions must be private (0600 - user rw only, no group or other permissions)
        assert (mode & 0o077) == 0, f"Socket permissions must be private, got {oct(mode)}"
    finally:
        listener.close()
        cleanup_linux_socket(sock_path)
    assert not os.path.exists(sock_path)


@pytest.mark.skipif(sys.platform == "win32", reason="Linux process group lifecycle tests require Linux")
def test_linux_owned_process_lifecycle(tmp_path):
    out_file = tmp_path / "child.out"
    err_file = tmp_path / "child.err"

    owned = OwnedProcess.launch(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout_path=out_file,
        stderr_path=err_file,
    )
    try:
        assert owned.alive() is True
        ident = owned.identity
        assert ident["pid"] == owned.pid
        assert ident["created"] > 0
        assert process_matches(ident) is True
    finally:
        owned.stop(timeout=3.0)

    assert owned.alive() is False
    assert process_matches(ident) is False


@pytest.mark.skipif(sys.platform == "win32", reason="Linux host-death process group cleanup tests require Linux")
def test_linux_owned_process_host_death_cleanup(tmp_path):
    status_file = tmp_path / "status.json"
    child_script = tmp_path / "child.py"
    host_script = tmp_path / "host.py"

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

    try:
        line = host_proc.stdout.readline()
        assert "HOST_READY" in line, f"Host failed to start: {line}, stderr: {host_proc.stderr.read()}"

        with open(status_file, "r", encoding="utf-8") as f:
            status = json.load(f)

        child_pid = status["child_pid"]
        grandchild_pid = status["grandchild_pid"]
        child_identity=process_identity(child_pid)
        grandchild_identity=process_identity(grandchild_pid)
        assert child_identity and grandchild_identity

        # Verify child and grandchild are actively running
        os.kill(child_pid, 0)
        os.kill(grandchild_pid, 0)

        # Forcibly kill host process (SIGKILL)
        host_proc.kill()
        host_proc.wait(timeout=5)

        # Verify supervisor detected EOF on lifetime pipe and killed entire process group
        deadline = time.monotonic() + 5.0
        child_dead = False
        grandchild_dead = False

        while time.monotonic() < deadline:
            child_dead=not process_matches(child_identity)
            grandchild_dead=not process_matches(grandchild_identity)

            if child_dead and grandchild_dead:
                break
            time.sleep(0.05)

        assert child_dead, f"Child process {child_pid} remained alive after host death"
        assert grandchild_dead, f"Grandchild process {grandchild_pid} remained alive after host death"

    finally:
        try:
            host_proc.kill()
        except Exception:
            pass
        host_proc.wait(timeout=5)


@pytest.mark.skipif(sys.platform=='win32',reason='Linux socket file protection')
def test_socket_cleanup_never_unlinks_regular_file(tmp_path):
    path=tmp_path/'not-a-socket';path.write_text('retain this file')
    with pytest.raises(ProtocolError,match='workspace_socket_path_occupied'):
        create_linux_listener(str(path))
    cleanup_linux_socket(str(path))
    assert path.read_text()=='retain this file'
