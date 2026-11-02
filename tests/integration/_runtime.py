"""Process and socket helpers for live-server integration tests."""

from __future__ import annotations

import csv
import io
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

_WINDOWS_PROCESS_TABLE_SCRIPT = (
    "Get-CimInstance Win32_Process | "
    "Select-Object ProcessId,ParentProcessId,"
    "@{Name='CreationTicks';Expression={"
    "if ($null -ne $_.CreationDate) { $_.CreationDate.ToUniversalTime().Ticks } else { '' }"
    "}} | "
    "ConvertTo-Csv -NoTypeInformation"
)
_WINDOWS_CREATION_TICKS: dict[int, int] = {}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, process: subprocess.Popen[str] | None = None, *, open_: bool) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.1)
            is_open = sock.connect_ex(("127.0.0.1", port)) == 0
        if is_open is open_:
            return
        if open_ and process is not None and process.poll() is not None:
            stdout, _ = process.communicate()
            message = f"server exited before readiness ({process.returncode}):\n{stdout}"
            raise AssertionError(message)
        time.sleep(0.05)
    message = f"port {port} did not become {'open' if open_ else 'closed'}"
    if process is not None:
        returncode = process.poll()
        liveness = "still running" if returncode is None else f"already exited with code {returncode}"
        message += f" (pid {process.pid} {liveness})"
    raise AssertionError(message)


def windows_executable(name: str, *parts: str) -> str:
    located = shutil.which(name)
    if located is not None:
        return located
    return str(Path(os.environ.get("SYSTEMROOT", "C:\\Windows")).joinpath(*parts, f"{name}.exe"))


def descendants(root_pid: int) -> set[int]:
    if sys.platform == "win32":
        table = _windows_process_table()
        found = _windows_descendants(table, root_pid)
        _record_windows_creation_ticks(table, (root_pid, *found))
        return found

    ps = shutil.which("ps") or "/bin/ps"
    output = subprocess.check_output([ps, "-eo", "pid=,ppid="], text=True)
    pairs = [
        (int(pid_text), int(parent_text)) for line in output.splitlines() for pid_text, parent_text in [line.split()]
    ]

    by_parent: dict[int, set[int]] = {}
    for pid, parent_pid in pairs:
        if pid != parent_pid:
            by_parent.setdefault(parent_pid, set()).add(pid)
    found = set()
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        for child in by_parent.get(parent, ()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def pid_exists(pid: int) -> bool:
    if sys.platform == "win32":
        if pid in _WINDOWS_CREATION_TICKS:
            return _windows_pid_matches(_windows_process_table(), pid)
        tasklist = windows_executable("tasklist", "System32")
        output = subprocess.check_output(
            [tasklist, "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True,
        )
        return any(len(row) > 1 and row[1] == str(pid) for row in csv.reader(io.StringIO(output)))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_descendants_to_exit(pids: set[int], *, parent_pid: int | None = None) -> None:
    if sys.platform == "win32":
        _wait_for_windows_descendants_to_exit(pids, parent_pid=parent_pid)
        return

    tracked_pids = set(pids)

    def current_pids() -> set[int]:
        if parent_pid is not None and pid_exists(parent_pid):
            tracked_pids.update(descendants(parent_pid))
        return tracked_pids

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(not pid_exists(pid) for pid in current_pids()):
            return
        time.sleep(0.05)
    remaining = sorted(pid for pid in current_pids() if pid_exists(pid))
    message = f"Granian descendants did not exit: {remaining}"
    raise AssertionError(message)


def wait_for_markers(marker: Path, value: str, count: int, *, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text(encoding="utf-8").splitlines().count(value) >= count:
            return
        time.sleep(0.05)
    message = f"marker {value!r} did not appear {count} times"
    raise AssertionError(message)


def start_process(command: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> subprocess.Popen[str]:
    if sys.platform == "win32":
        return subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def finish_process(process: subprocess.Popen[str], timeout: float) -> str:
    stdout, _ = process.communicate(timeout=timeout)
    return stdout if stdout is not None else ""


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        taskkill = windows_executable("taskkill", "System32")
        subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"], check=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def _wait_for_windows_descendants_to_exit(pids: set[int], *, parent_pid: int | None = None) -> None:
    """Wait until all tracked Windows descendants exit, accounting for PID reuse."""
    tracked_pids = set(pids)
    deadline = time.monotonic() + 5
    remaining: list[int] = []
    while True:
        table = _windows_process_table()
        if parent_pid is not None and _windows_pid_matches(table, parent_pid):
            current_children = _windows_descendants(table, parent_pid)
            _record_windows_creation_ticks(table, current_children)
            tracked_pids.update(current_children)
        remaining = sorted(pid for pid in tracked_pids if _windows_pid_matches(table, pid))
        if not remaining or time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    if remaining:
        message = f"Granian descendants did not exit: {remaining}"
        raise AssertionError(message)


def _windows_process_table() -> dict[int, tuple[int, int | None]]:
    """Query active Windows processes mapped to ``(parent_pid, creation_ticks)``."""
    powershell = windows_executable(
        "powershell",
        "System32",
        "WindowsPowerShell",
        "v1.0",
    )
    output = subprocess.check_output(
        [powershell, "-NoProfile", "-Command", _WINDOWS_PROCESS_TABLE_SCRIPT],
        text=True,
    )
    return _parse_windows_process_table(output)


def _parse_windows_process_table(output: str) -> dict[int, tuple[int, int | None]]:
    """Parse ``Win32_Process`` CSV rows into ``pid -> (parent_pid, creation_ticks)``."""
    rows = csv.DictReader(io.StringIO(output))
    table: dict[int, tuple[int, int | None]] = {}
    for row in rows:
        raw_pid = row.get("ProcessId")
        raw_parent = row.get("ParentProcessId")
        if not raw_pid or not raw_parent:
            continue
        raw_ticks = (row.get("CreationTicks") or "").strip()
        ticks = int(raw_ticks) if raw_ticks else None
        table[int(raw_pid)] = (int(raw_parent), ticks)
    return table


def _windows_descendants(table: Mapping[int, tuple[int, int | None]], root_pid: int) -> set[int]:
    """Return Windows descendants created at or after each parent in the chain."""
    root_entry = table.get(root_pid)
    if root_entry is None or root_entry[1] is None:
        return set()
    children_by_parent = _windows_valid_children_by_parent(table)
    found: set[int] = set()
    pending = [root_pid]
    while pending:
        for child in children_by_parent.get(pending.pop(), ()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def _windows_valid_children_by_parent(
    table: Mapping[int, tuple[int, int | None]],
) -> dict[int, set[int]]:
    """Group candidate child PIDs whose creation timestamp is not older than their parent."""
    by_parent: dict[int, set[int]] = {}
    for pid, (parent_pid, child_ticks) in table.items():
        if pid == parent_pid or child_ticks is None:
            continue
        parent_entry = table.get(parent_pid)
        if parent_entry is None or parent_entry[1] is None:
            continue
        if child_ticks >= parent_entry[1]:
            by_parent.setdefault(parent_pid, set()).add(pid)
    return by_parent


def _record_windows_creation_ticks(
    table: Mapping[int, tuple[int, int | None]],
    pids: Iterable[int],
) -> None:
    """Cache observed creation timestamps so recycled PIDs are not treated as still running."""
    for pid in pids:
        entry = table.get(pid)
        if entry is not None and entry[1] is not None:
            _WINDOWS_CREATION_TICKS[pid] = entry[1]
        else:
            _WINDOWS_CREATION_TICKS.pop(pid, None)


def _windows_pid_matches(table: Mapping[int, tuple[int, int | None]], pid: int) -> bool:
    """Return whether ``pid`` still refers to the originally observed Windows process."""
    entry = table.get(pid)
    if entry is None:
        return False
    expected_ticks = _WINDOWS_CREATION_TICKS.get(pid)
    if expected_ticks is None:
        return True
    return entry[1] == expected_ticks
