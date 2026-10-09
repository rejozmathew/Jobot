"""Linux process and group lifecycle helpers for the workspace host.

Provides:
- Linux /proc cmdline inventory matching exact resolved --user-data-dir.
- Owned browser process/group lifecycle with reliable host-death cleanup
  via a dedicated supervisor watching a non-inherited lifetime pipe and killing
  its process group on EOF.
- UNIX domain socket listener with private (0600) permissions.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from .managed_shared import ProtocolError

SIGKILL = getattr(signal, "SIGKILL", 9)
SIGTERM = getattr(signal, "SIGTERM", 15)


# -----------------------------------------------------------------------------
# Command Line Parsing and /proc Inventory
# -----------------------------------------------------------------------------

def parse_cmdline_args(cmdline_data: Union[bytes, str, Sequence[str]]) -> List[str]:
    """Parse raw /proc cmdline bytes, string, or argv list into argument list."""
    if isinstance(cmdline_data, bytes):
        decoded = cmdline_data.decode("utf-8", errors="replace")
        if "\0" in decoded:
            return [arg for arg in decoded.split("\0") if arg]
        import shlex
        try:
            return shlex.split(decoded)
        except ValueError:
            return decoded.split()
    elif isinstance(cmdline_data, str):
        if "\0" in cmdline_data:
            return [arg for arg in cmdline_data.split("\0") if arg]
        import shlex
        try:
            return shlex.split(cmdline_data)
        except ValueError:
            return cmdline_data.split()
    elif isinstance(cmdline_data, (list, tuple)):
        return [str(a) for a in cmdline_data]
    return []


def extract_user_data_dir(args: Sequence[str]) -> Optional[str]:
    """Extract raw --user-data-dir value from command line arguments."""
    for idx, arg in enumerate(args):
        if arg.startswith("--user-data-dir="):
            val = arg.split("=", 1)[1]
            return val.strip("'\"")
        elif arg == "--user-data-dir":
            if idx + 1 < len(args):
                return args[idx + 1].strip("'\"")
    return None


def cmdline_matches_user_data_dir(
    cmdline_data: Union[bytes, str, Sequence[str]],
    target_user_data_dir: Union[str, Path],
    case_sensitive: Optional[bool] = None,
    base_cwd: Optional[Union[str, Path]] = None,
) -> bool:
    """Return True if cmdline arguments contain an exact match for target_user_data_dir."""
    args = parse_cmdline_args(cmdline_data)
    candidate = extract_user_data_dir(args)
    if not candidate:
        return False

    try:
        path=Path(candidate)
        if not path.is_absolute() and base_cwd is not None:path=Path(base_cwd)/path
        cand_resolved = str(path.resolve())
        target_resolved = str(Path(target_user_data_dir).resolve())
    except Exception:
        return False

    if case_sensitive is None:
        case_sensitive = (os.name != "nt")

    if case_sensitive:
        return cand_resolved == target_resolved
    return cand_resolved.casefold() == target_resolved.casefold()


def linux_profile_in_use(
    workspace: Dict[str, Any],
    proc_path: Union[str, Path] = "/proc",
    case_sensitive: Optional[bool] = None,
    *, browser_root_only: bool = False,
) -> Optional[int]:
    """Inspect Linux /proc for any running process using workspace['user_data_dir'].

    Never kills or terminates other browsers.
    Handles exited processes and permission restrictions honestly.
    """
    proc_dir = Path(proc_path)
    if not proc_dir.is_dir():
        raise ProtocolError(
            "workspace_process_inventory_unavailable",
            f"Process inventory directory unavailable: {proc_path}",
        )

    target_user_data_dir = workspace.get("user_data_dir")
    if not target_user_data_dir:
        return None

    try:
        entries = os.listdir(proc_dir)
    except (PermissionError, OSError) as exc:
        raise ProtocolError(
            "workspace_process_inventory_unavailable",
            f"Cannot list process directory {proc_path}: {exc}",
        ) from exc

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)

        cmdline_file = proc_dir / entry / "cmdline"
        try:
            with open(cmdline_file, "rb") as f:
                data = f.read()
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as exc:
            # An unreadable process of our user cannot prove the profile is free.
            try:
                same_user=(proc_dir/entry).stat().st_uid==os.getuid()
            except (OSError,AttributeError):same_user=True
            if same_user:raise ProtocolError('workspace_process_inventory_unavailable') from exc
            continue
        except OSError:
            continue

        if not data:
            continue

        if browser_root_only:
            args = parse_cmdline_args(data)
            if any(arg == '--type' or arg.startswith('--type=') for arg in args):
                continue

        if cmdline_matches_user_data_dir(data, target_user_data_dir, case_sensitive=case_sensitive,
                                        base_cwd=proc_dir/entry/'cwd'):
            # Verify process is still running and not a zombie
            stat_file = proc_dir / entry / "stat"
            try:
                with open(stat_file, "r", encoding="utf-8") as sf:
                    stat_content = sf.read()
                comm_end = stat_content.rfind(")")
                if comm_end != -1:
                    fields = stat_content[comm_end + 2:].split()
                    if fields and fields[0] == "Z":
                        continue
            except Exception:
                pass

            return pid

    return None


# -----------------------------------------------------------------------------
# UNIX Domain Socket Helpers
# -----------------------------------------------------------------------------

def create_linux_listener(address: str) -> Any:
    """Create a multiprocessing Listener on AF_UNIX with private (0600) permissions."""
    from multiprocessing.connection import Listener
    import stat
    if os.path.lexists(address):
        info=os.lstat(address)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid():
            raise ProtocolError('workspace_socket_path_occupied')
        os.unlink(address)

    old_umask = os.umask(0o077)
    try:
        listener = Listener(address, family="AF_UNIX", authkey=None)
        os.chmod(address, 0o600)
        return listener
    finally:
        os.umask(old_umask)


def cleanup_linux_socket(address: str) -> None:
    """Safely unlink a UNIX domain socket file."""
    try:
        import stat
        info=os.lstat(address)
        if stat.S_ISSOCK(info.st_mode) and info.st_uid==os.getuid():
            os.unlink(address)
    except OSError:
        pass


# -----------------------------------------------------------------------------
# Process Group Lifecycle & Supervisor
# -----------------------------------------------------------------------------

def linux_launch_owned_process(
    cls: Any,
    argv: Sequence[str],
    cwd: Optional[Union[str, Path]] = None,
    stdout_path: Optional[Union[str, Path]] = None,
    stderr_path: Optional[Union[str, Path]] = None,
) -> Any:
    """Launch a process inside a dedicated Linux process group with host-death cleanup."""
    lifetime_r, lifetime_w = os.pipe()
    notify_r, notify_w = os.pipe()

    if hasattr(os, "set_inheritable"):
        os.set_inheritable(lifetime_r, True)
        os.set_inheritable(lifetime_w, False)
        os.set_inheritable(notify_w, True)
        os.set_inheritable(notify_r, False)

    sup_cmd = [
        sys.executable,
        "-m", "job_applier.workspace_linux",
        "supervisor",
        f"--lifetime-fd={lifetime_r}",
        f"--notify-fd={notify_w}",
    ]
    if cwd:
        sup_cmd.append(f"--cwd={cwd}")
    if stdout_path:
        sup_cmd.append(f"--stdout={stdout_path}")
    if stderr_path:
        sup_cmd.append(f"--stderr={stderr_path}")
    sup_cmd.append("--")
    sup_cmd.extend(argv)

    sup_proc = None
    try:
        sup_proc = subprocess.Popen(
            sup_cmd,
            pass_fds=(lifetime_r, notify_w) if sys.platform != "win32" else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except BaseException:
        os.close(lifetime_w);os.close(notify_r)
        raise
    finally:
        try:
            os.close(lifetime_r)
        except OSError:
            pass
        try:
            os.close(notify_w)
        except OSError:
            pass

    try:
        import select
        if not select.select([notify_r],[],[],10)[0]:
            os.close(notify_r)
            raise ProtocolError('job_setup_failed','Supervisor startup notification timed out')
        with os.fdopen(notify_r, "r", encoding="utf-8") as f:
            raw_payload = f.read()
    except Exception as exc:
        try:
            os.close(lifetime_w)
        except OSError:
            pass
        raise ProtocolError("job_setup_failed", f"Failed to read supervisor notification: {exc}") from exc

    if not raw_payload:
        try:
            os.close(lifetime_w)
        except OSError:
            pass
        raise ProtocolError("job_setup_failed", "Supervisor exited before sending notification")

    try:
        payload = json.loads(raw_payload)
    except Exception as exc:
        try:
            os.close(lifetime_w)
        except OSError:
            pass
        raise ProtocolError("job_setup_failed", f"Malformed supervisor notification: {raw_payload}") from exc

    if "error" in payload:
        try:
            os.close(lifetime_w)
        except OSError:
            pass
        raise ProtocolError("job_setup_failed", payload["error"])

    browser_pid = payload["browser_pid"]
    pgid = payload["pgid"]
    created = payload.get("created", 0)

    from .workspace_process import process_identity
    if not created:
        ident = process_identity(browser_pid)
        if ident:
            created = ident["created"]

    identity = {"pid": browser_pid, "created": created}

    return cls(
        pid=browser_pid,
        identity=identity,
        pgid=pgid,
        lifetime_w=lifetime_w,
        supervisor_proc=sup_proc,
    )


def linux_stop_owned_process(
    pgid: Optional[int],
    pid: int,
    identity: Dict[str, Any],
    lifetime_w: Optional[int],
    supervisor_proc: Optional[Any],
    timeout: float = 5.0,
) -> None:
    """Request cleanup through the owned pipe, never signal a potentially reused PGID."""
    from .workspace_process import process_matches
    if lifetime_w is not None:
        try:
            os.close(lifetime_w)
        except OSError:
            pass
    deadline = time.monotonic() + (timeout if timeout is not None else 5.0)
    while time.monotonic() < deadline:
        if not process_matches(identity) and supervisor_proc is not None and supervisor_proc.poll() is not None:
            return
        time.sleep(0.05)
    raise ProtocolError('owned_process_stop_unconfirmed')


def supervisor_main(args: Sequence[str]) -> None:
    """Entry point for supervisor subprocess watching lifetime pipe."""
    parser = argparse.ArgumentParser(description="Linux OwnedProcess supervisor")
    parser.add_argument("--lifetime-fd", type=int, required=True)
    parser.add_argument("--notify-fd", type=int, required=True)
    parser.add_argument("--cwd", type=str, default=None)
    parser.add_argument("--stdout", type=str, default=None)
    parser.add_argument("--stderr", type=str, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)

    parsed = parser.parse_args(args)
    cmd = parsed.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        sys.exit("No command provided to supervisor")

    if hasattr(os, "setpgrp"):
        os.setpgrp()
    elif hasattr(os, "setpgid"):
        os.setpgid(0, 0)
    my_pgid = os.getpgrp() if hasattr(os, "getpgrp") else os.getpid()

    # The supervisor MUST survive its parent's death long enough to read EOF.
    # PR_SET_PDEATHSIG(SIGKILL) here would kill it before group cleanup could run.
    def kill_own_group(*unused):
        os.killpg(os.getpgrp(),SIGKILL)
    signal.signal(SIGTERM,kill_own_group)
    signal.signal(signal.SIGINT,kill_own_group)

    stdout_f = None
    stderr_f = None
    try:
        if parsed.stdout:
            p_out = Path(parsed.stdout)
            p_out.parent.mkdir(parents=True, exist_ok=True)
            stdout_f = open(p_out, "ab")
        else:
            stdout_f = subprocess.DEVNULL

        if parsed.stderr:
            if parsed.stdout and str(Path(parsed.stderr).resolve()) == str(Path(parsed.stdout).resolve()):
                stderr_f = stdout_f
            else:
                p_err = Path(parsed.stderr)
                p_err.parent.mkdir(parents=True, exist_ok=True)
                stderr_f = open(p_err, "ab")
        else:
            stderr_f = subprocess.DEVNULL
    except Exception as exc:
        try:
            with open(parsed.notify_fd, "w", encoding="utf-8") as nf:
                json.dump({"error": f"Failed to prepare stdout/stderr: {exc}"}, nf)
        except Exception:
            pass
        sys.exit(1)

    try:
        child_proc = subprocess.Popen(
            cmd,
            cwd=parsed.cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout_f,
            stderr=stderr_f,
            close_fds=True,
        )
    except Exception as exc:
        try:
            with open(parsed.notify_fd, "w", encoding="utf-8") as nf:
                json.dump({"error": f"Failed to launch target process {cmd}: {exc}"}, nf)
        except Exception:
            pass
        sys.exit(1)

    # Close file handles in supervisor so only child process holds write ends
    if stdout_f not in (None, subprocess.DEVNULL):
        try:
            stdout_f.close()
        except OSError:
            pass
    if stderr_f not in (None, subprocess.DEVNULL, stdout_f):
        try:
            stderr_f.close()
        except OSError:
            pass

    from .workspace_process import process_identity
    ident = process_identity(child_proc.pid)
    created = ident["created"] if ident else 0

    try:
        with open(parsed.notify_fd, "w", encoding="utf-8") as nf:
            json.dump({
                "browser_pid": child_proc.pid,
                "supervisor_pid": os.getpid(),
                "pgid": my_pgid,
                "created": created,
            }, nf)
    except Exception:
        try:
            child_proc.kill()
        except Exception:
            pass
        sys.exit(1)

    def watch_lifetime_pipe():
        try:
            while True:
                data = os.read(parsed.lifetime_fd, 1024)
                if not data:
                    break
        except Exception:
            pass
        # Host closed pipe or died: kill entire process group
        try:
            if hasattr(os, "killpg"):
                os.killpg(my_pgid, SIGKILL)
            elif hasattr(os, "kill"):
                os.kill(-my_pgid, SIGKILL)
        except Exception:
            pass
        try:
            child_proc.kill()
        except Exception:
            pass
        os._exit(0)

    t = threading.Thread(target=watch_lifetime_pipe, daemon=True)
    t.start()

    child_proc.wait()
    # Even a normal root-process exit must not leave its group descendants alive.
    kill_own_group()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "supervisor":
        supervisor_main(sys.argv[2:])
    else:
        sys.exit("Usage: python -m job_applier.workspace_linux supervisor ...")
