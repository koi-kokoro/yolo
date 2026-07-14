"""Small, injectable cross-platform subprocess adapter for online training."""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import IO, Callable


class TrainingProcessAdapter:
    def __init__(self, popen: Callable = subprocess.Popen):
        self._popen = popen
        self._processes: dict[int, subprocess.Popen] = {}
        self._logs: dict[int, IO[bytes]] = {}

    def spawn(self, argv: list[str], cwd: Path, log_path: Path) -> subprocess.Popen:
        if not argv or not all(isinstance(value, str) for value in argv):
            raise ValueError("argv must be a non-empty string array")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("ab", buffering=0)
        kwargs = {
            "args": argv,
            "cwd": str(cwd),
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "shell": False,
            "close_fds": os.name != "nt",
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            process = self._popen(**kwargs)
        except Exception:
            log.close()
            raise
        self._processes[process.pid] = process
        self._logs[process.pid] = log
        return process

    def poll(self, pid: int) -> int | None:
        process = self._processes.get(pid)
        return process.poll() if process is not None else None

    def graceful_stop(self, pid: int) -> bool:
        process = self._processes.get(pid)
        if process is None or process.poll() is not None:
            return False
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        return True

    def force_stop(self, pid: int) -> bool:
        process = self._processes.get(pid)
        if process is None or process.poll() is not None:
            return False
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        return True

    def forget(self, pid: int) -> None:
        self._processes.pop(pid, None)
        log = self._logs.pop(pid, None)
        if log is not None:
            log.close()

    def owns(self, pid: int) -> bool:
        return pid in self._processes


training_process = TrainingProcessAdapter()
