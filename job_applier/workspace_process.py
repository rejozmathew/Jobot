"""Windows process and lock primitives for the application session host."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Set, Tuple, Union

from .managed_shared import ProtocolError


# -----------------------------------------------------------------------------
# OS Setup and 64-bit Win32 Signatures
# -----------------------------------------------------------------------------

_IS_WIN32 = sys.platform == "win32"

if _IS_WIN32:
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Constants
    WAIT_TIMEOUT = 0x00000102
    WAIT_OBJECT_0 = 0x00000000
    INFINITE = 0xFFFFFFFF

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    PROCESS_TERMINATE = 0x0001

    CREATE_SUSPENDED = 0x00000004
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000

    STARTF_USESTDHANDLES = 0x00000100
    HANDLE_FLAG_INHERIT = 0x00000001

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
    JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
    JobObjectExtendedLimitInformation = 9

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    OPEN_ALWAYS = 4
    FILE_ATTRIBUTE_NORMAL = 0x00000080
    FILE_END = 2
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    # Structures
    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
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

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    class STARTUPINFOW(ctypes.Structure):
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
            ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    # Function prototypes
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL

    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE

    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL

    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL

    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL

    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL

    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD

    kernel32.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
    kernel32.SetHandleInformation.restype = wintypes.BOOL

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    kernel32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    kernel32.IsProcessInJob.restype = wintypes.BOOL

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE

    kernel32.SetFilePointer.argtypes = [
        wintypes.HANDLE,
        wintypes.LONG,
        ctypes.POINTER(wintypes.LONG),
        wintypes.DWORD,
    ]
    kernel32.SetFilePointer.restype = wintypes.DWORD

    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL
else:
    try:
        import fcntl
    except ImportError:
        fcntl = None  # type: ignore


# -----------------------------------------------------------------------------
# FileLock
# -----------------------------------------------------------------------------

_PROCESS_LOCKS: Set[str] = set()
_PROCESS_LOCKS_GUARD = threading.Lock()


class FileLock:
    """Nonblocking OS-backed file lock.

    Guarantees:
    - Nonblocking acquire() raises ProtocolError('local_lock_busy') if already locked.
    - Thread callers in the same process and process callers cannot share the same lock.
    - Lock files remain on disk when released.
    - Releases cleanly on release(), exit, or process termination.
    - static is_locked(path) probes lock state without deleting.
    """

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._norm_path = os.path.normcase(os.path.abspath(str(path)))
        self._fd: Optional[int] = None
        self._acquired = False

    def acquire(self) -> "FileLock":
        if self._acquired:
            raise ProtocolError("local_lock_busy", f"Lock already acquired by instance: {self.path}")

        with _PROCESS_LOCKS_GUARD:
            if self._norm_path in _PROCESS_LOCKS:
                raise ProtocolError("local_lock_busy", f"Lock already held in this process: {self.path}")

            # Ensure parent directory exists
            parent = os.path.dirname(self._norm_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
            try:
                fd = os.open(self._norm_path, flags, 0o666)
            except OSError as exc:
                raise ProtocolError("local_lock_busy", f"Cannot open lock file {self.path}: {exc}") from exc

            try:
                if _IS_WIN32:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, IOError) as exc:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise ProtocolError("local_lock_busy", f"Lock is busy: {self.path} ({exc})") from exc

            _PROCESS_LOCKS.add(self._norm_path)
            self._fd = fd
            self._acquired = True
            return self

    def release(self) -> None:
        with _PROCESS_LOCKS_GUARD:
            if not self._acquired or self._fd is None:
                return
            fd = self._fd
            self._fd = None
            self._acquired = False
            _PROCESS_LOCKS.discard(self._norm_path)
            try:
                if _IS_WIN32:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    @staticmethod
    def is_locked(path: Union[str, Path]) -> bool:
        """Probe lock status without deleting the lock file."""
        norm = os.path.normcase(os.path.abspath(str(path)))
        with _PROCESS_LOCKS_GUARD:
            if norm in _PROCESS_LOCKS:
                return True

        if not os.path.exists(norm):
            return False

        flags = os.O_RDWR | getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(norm, flags)
        except (OSError, IOError):
            # File cannot be opened (e.g. sharing violation or lock held)
            return True

        try:
            if _IS_WIN32:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                except (OSError, IOError):
                    return True
                else:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    return False
            elif fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, IOError):
                    return True
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    return False
            else:
                return False
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


# -----------------------------------------------------------------------------
# Process Identity
# -----------------------------------------------------------------------------

def process_identity(pid: int) -> Optional[Dict[str, Any]]:
    """Return {pid: int, created: int} from real OS process start timestamp.

    Returns None if missing or already terminated.
    """
    if not isinstance(pid, int) or pid <= 0:
        return None

    if _IS_WIN32:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not h:
            return None
        try:
            # Must be actively running (not signaled/terminated)
            res = kernel32.WaitForSingleObject(h, 0)
            if res != WAIT_TIMEOUT:
                return None
            ct = FILETIME()
            et = FILETIME()
            kt = FILETIME()
            ut = FILETIME()
            if not kernel32.GetProcessTimes(h, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)):
                return None
            created = (ct.dwHighDateTime << 32) | ct.dwLowDateTime
            return {"pid": pid, "created": created}
        finally:
            kernel32.CloseHandle(h)
    else:
        stat_path = f"/proc/{pid}/stat"
        if not os.path.exists(stat_path):
            return None
        try:
            with open(stat_path, "r", encoding="utf-8") as f:
                content = f.read()
            comm_end = content.rfind(")")
            if comm_end == -1:
                return None
            fields = content[comm_end + 2:].split()
            if fields[0]=='Z':return None
            # starttime is field 22 (index 19 after pid and comm)
            starttime = int(fields[19])
            return {"pid": pid, "created": starttime}
        except Exception:
            return None


def process_matches(identity: Any) -> bool:
    """Verify creation time AND running status, never PID alone."""
    if not isinstance(identity, dict):
        return False
    pid = identity.get("pid")
    created = identity.get("created")
    if not isinstance(pid, int) or pid <= 0 or created is None:
        return False

    curr = process_identity(pid)
    if curr is None:
        return False
    return curr.get("created") == created


# -----------------------------------------------------------------------------
# OwnedProcess
# -----------------------------------------------------------------------------

class OwnedProcess:
    """Windows child process assigned to a dedicated Job Object with KILL_ON_JOB_CLOSE.

    Avoids child handle inheritance of the job handle so that host crash
    reliably kills browser descendants.
    """

    def __init__(
        self,
        pid: int,
        identity: Dict[str, Any],
        proc_handle: Any,
        job_handle: Any,
        open_handles: Optional[Sequence[Any]] = None,
    ):
        self._pid = pid
        self._identity = identity
        self._proc_handle = proc_handle
        self._job_handle = job_handle
        self._open_handles = list(open_handles or [])
        self._stopped = False

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def identity(self) -> Dict[str, Any]:
        return dict(self._identity)

    def alive(self) -> bool:
        if self._stopped or not self._proc_handle:
            return False
        if _IS_WIN32:
            res = kernel32.WaitForSingleObject(self._proc_handle, 0)
            return res == WAIT_TIMEOUT
        return False

    def stop(self, timeout: float = 5.0) -> None:
        """Kill ONLY that owned job and wait for child death."""
        if self._stopped:
            return

        if _IS_WIN32:
            if self._job_handle:
                if not kernel32.TerminateJobObject(self._job_handle, 1):
                    raise ProtocolError('owned_process_stop_failed',str(ctypes.get_last_error()))
            if self._proc_handle:
                timeout_ms = int(timeout * 1000) if timeout is not None else 5000
                if kernel32.WaitForSingleObject(self._proc_handle, timeout_ms)!=WAIT_OBJECT_0:
                    raise ProtocolError('owned_process_stop_unconfirmed')
            self._cleanup()
        self._stopped = True

    close = stop

    def _cleanup(self) -> None:
        if _IS_WIN32:
            for h in self._open_handles:
                if h and h != INVALID_HANDLE_VALUE:
                    try:
                        kernel32.CloseHandle(h)
                    except Exception:
                        pass
            self._open_handles.clear()

            if self._proc_handle:
                try:
                    kernel32.CloseHandle(self._proc_handle)
                except Exception:
                    pass
                self._proc_handle = None

            if self._job_handle:
                try:
                    kernel32.CloseHandle(self._job_handle)
                except Exception:
                    pass
                self._job_handle = None

    def __enter__(self) -> "OwnedProcess":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    @classmethod
    def launch(
        cls,
        argv: Sequence[str],
        cwd: Optional[Union[str, Path]] = None,
        stdout_path: Optional[Union[str, Path]] = None,
        stderr_path: Optional[Union[str, Path]] = None,
    ) -> "OwnedProcess":
        if not _IS_WIN32:
            raise NotImplementedError("OwnedProcess is only supported on Windows")

        # 1. Create a dedicated Windows Job Object
        job_handle = kernel32.CreateJobObjectW(None, None)
        if not job_handle:
            err = ctypes.get_last_error()
            raise ProtocolError("job_setup_failed", f"Failed to create Job Object: {err}")

        # Explicitly ensure the job handle is NOT inheritable by child processes
        kernel32.SetHandleInformation(job_handle, HANDLE_FLAG_INHERIT, 0)

        # 2. Configure KILL_ON_JOB_CLOSE
        job_info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        job_info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        res = kernel32.SetInformationJobObject(
            job_handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(job_info),
            ctypes.sizeof(job_info),
        )
        if not res:
            err = ctypes.get_last_error()
            kernel32.CloseHandle(job_handle)
            raise ProtocolError("job_setup_failed", f"Failed to set KILL_ON_JOB_CLOSE on job: {err}")

        # 3. Setup standard output/error handle redirection with inheritance
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.bInheritHandle = True
        sa.lpSecurityDescriptor = None

        h_stdout = None
        h_stderr = None
        h_stdin = None
        extra_handles = []

        try:
            if stdout_path:
                p_out = Path(stdout_path)
                p_out.parent.mkdir(parents=True, exist_ok=True)
                h_stdout = kernel32.CreateFileW(
                    str(p_out),
                    GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                    ctypes.byref(sa),
                    OPEN_ALWAYS,
                    FILE_ATTRIBUTE_NORMAL,
                    None,
                )
                if h_stdout == INVALID_HANDLE_VALUE:
                    err = ctypes.get_last_error()
                    raise OSError(f"Failed to open stdout file {stdout_path}: {err}")
                kernel32.SetFilePointer(h_stdout, 0, None, FILE_END)
                extra_handles.append(h_stdout)

            if stderr_path:
                if stdout_path and str(Path(stderr_path).resolve()) == str(Path(stdout_path).resolve()):
                    h_stderr = h_stdout
                else:
                    p_err = Path(stderr_path)
                    p_err.parent.mkdir(parents=True, exist_ok=True)
                    h_stderr = kernel32.CreateFileW(
                        str(p_err),
                        GENERIC_WRITE,
                        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                        ctypes.byref(sa),
                        OPEN_ALWAYS,
                        FILE_ATTRIBUTE_NORMAL,
                        None,
                    )
                    if h_stderr == INVALID_HANDLE_VALUE:
                        err = ctypes.get_last_error()
                        raise OSError(f"Failed to open stderr file {stderr_path}: {err}")
                    kernel32.SetFilePointer(h_stderr, 0, None, FILE_END)
                    extra_handles.append(h_stderr)

            # 4. Prepare STARTUPINFOW
            si = STARTUPINFOW()
            si.cb = ctypes.sizeof(STARTUPINFOW)
            si.dwFlags = 0

            inherit_handles = bool(h_stdout is not None or h_stderr is not None)
            if inherit_handles:
                h_stdin = kernel32.CreateFileW(
                    r"\\.\NUL",
                    GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    ctypes.byref(sa),
                    OPEN_EXISTING,
                    0,
                    None,
                )
                if h_stdin != INVALID_HANDLE_VALUE:
                    extra_handles.append(h_stdin)
                si.dwFlags |= STARTF_USESTDHANDLES
                si.hStdInput = h_stdin if h_stdin != INVALID_HANDLE_VALUE else None
                si.hStdOutput = h_stdout if h_stdout is not None else si.hStdInput
                si.hStdError = h_stderr if h_stderr is not None else si.hStdInput

            # 5. Launch child process SUSPENDED
            cmd_line = subprocess.list2cmdline(argv) if isinstance(argv, (list, tuple)) else str(argv)
            cwd_str = str(cwd) if cwd is not None else None
            creation_flags = CREATE_SUSPENDED | CREATE_NO_WINDOW
            pi = PROCESS_INFORMATION()

            res = kernel32.CreateProcessW(
                None,
                cmd_line,
                None,
                None,
                inherit_handles,
                creation_flags,
                None,
                cwd_str,
                ctypes.byref(si),
                ctypes.byref(pi),
            )
            if not res:
                err = ctypes.get_last_error()
                raise OSError(f"CreateProcessW failed for {argv}: {err}")

            # 6. Assign process to Job Object BEFORE resuming thread
            assign_res = kernel32.AssignProcessToJobObject(job_handle, pi.hProcess)
            if not assign_res:
                err = ctypes.get_last_error()
                # Do not silently degrade kill-on-host-death guarantees!
                kernel32.TerminateProcess(pi.hProcess, 1)
                kernel32.CloseHandle(pi.hThread)
                kernel32.CloseHandle(pi.hProcess)
                kernel32.CloseHandle(job_handle)
                for h in extra_handles:
                    kernel32.CloseHandle(h)
                raise ProtocolError(
                    "job_assignment_failed",
                    f"Failed to assign child process to Job Object: {err}",
                )

            # 7. Get identity from process times before resuming
            ct = FILETIME()
            et = FILETIME()
            kt = FILETIME()
            ut = FILETIME()
            if kernel32.GetProcessTimes(pi.hProcess, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)):
                created = (ct.dwHighDateTime << 32) | ct.dwLowDateTime
            else:
                created = 0
            ident = {"pid": pi.dwProcessId, "created": created}

            # 8. Resume child thread
            kernel32.ResumeThread(pi.hThread)
            kernel32.CloseHandle(pi.hThread)

            return cls(
                pid=pi.dwProcessId,
                identity=ident,
                proc_handle=pi.hProcess,
                job_handle=job_handle,
                open_handles=extra_handles,
            )

        except Exception:
            for h in extra_handles:
                try:
                    kernel32.CloseHandle(h)
                except Exception:
                    pass
            kernel32.CloseHandle(job_handle)
            raise


# -----------------------------------------------------------------------------
# Detached Launch
# -----------------------------------------------------------------------------

def check_breakaway_permitted() -> Tuple[bool, str]:
    """Check if the current process is permitted to break away from an enclosing Job Object.

    Returns (is_permitted, reason_if_denied).
    """
    if not _IS_WIN32:
        return True, ""

    in_job = wintypes.BOOL()
    if not kernel32.IsProcessInJob(kernel32.GetCurrentProcess(), None, ctypes.byref(in_job)):
        return True, ""

    if not in_job.value:
        # Not in any Job Object: breakaway is naturally allowed/unconstrained
        return True, ""

    # In a Job Object: query if JOB_OBJECT_LIMIT_BREAKAWAY_OK or SILENT_BREAKAWAY_OK is set
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    ret_len = wintypes.DWORD()
    if kernel32.QueryInformationJobObject(None, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(ret_len)):
        flags = info.BasicLimitInformation.LimitFlags
        if flags & (JOB_OBJECT_LIMIT_BREAKAWAY_OK | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK):
            return True, ""
        else:
            return (
                False,
                "Process is in a Windows Job Object that prohibits breakaway (JOB_OBJECT_LIMIT_BREAKAWAY_OK is not set). "
                "Detached session host cannot survive parent job termination.",
            )

    return True, ""


def detached_launch(
    argv: Sequence[str],
    cwd: Optional[Union[str, Path]] = None,
    stdout_path: Optional[Union[str, Path]] = None,
    stderr_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Launch a detached session host that survives a short-lived CLI shell.

    Uses Popen with OS detachment, process group, and Windows breakaway if permitted,
    no console popup, standard handles redirected, close_fds.
    If breakaway is denied, reports an actionable ProtocolError('breakaway_denied').
    Returns the process identity dict.
    """
    if _IS_WIN32:
        permitted, reason = check_breakaway_permitted()
        if not permitted:
            raise ProtocolError("breakaway_denied", reason)

        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        if permitted:
            # Check if in a job; if so, pass CREATE_BREAKAWAY_FROM_JOB
            in_job = wintypes.BOOL()
            if kernel32.IsProcessInJob(kernel32.GetCurrentProcess(), None, ctypes.byref(in_job)) and in_job.value:
                flags |= CREATE_BREAKAWAY_FROM_JOB
    else:
        flags = 0

    stdout_file = None
    stderr_file = None

    try:
        if stdout_path:
            p_out = Path(stdout_path)
            p_out.parent.mkdir(parents=True, exist_ok=True)
            stdout_file = open(p_out, "ab")
        else:
            stdout_file = subprocess.DEVNULL

        if stderr_path:
            if stdout_path and str(Path(stderr_path).resolve()) == str(Path(stdout_path).resolve()):
                stderr_file = stdout_file
            else:
                p_err = Path(stderr_path)
                p_err.parent.mkdir(parents=True, exist_ok=True)
                stderr_file = open(p_err, "ab")
        else:
            stderr_file = subprocess.DEVNULL

        popen_kwargs: Dict[str, Any] = {
            "cwd": str(cwd) if cwd is not None else None,
            "stdin": subprocess.DEVNULL,
            "stdout": stdout_file,
            "stderr": stderr_file,
            "close_fds": True,
        }

        if _IS_WIN32:
            popen_kwargs["creationflags"] = flags
        else:
            popen_kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(argv, **popen_kwargs)
        except PermissionError as exc:
            if getattr(exc, "winerror", None) == 5:
                raise ProtocolError(
                    "breakaway_denied",
                    "Windows denied process breakaway from job object (ERROR_ACCESS_DENIED).",
                ) from exc
            raise

    finally:
        if stdout_file not in (None, subprocess.DEVNULL):
            try:
                stdout_file.close()
            except OSError:
                pass
        if stderr_file not in (None, subprocess.DEVNULL, stdout_file):
            try:
                stderr_file.close()
            except OSError:
                pass

    ident = process_identity(proc.pid)
    if ident is None:
        raise ProtocolError('host_exited_during_launch')
    return ident
