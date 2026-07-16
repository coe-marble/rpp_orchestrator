from __future__ import annotations

"""Deprecated: script runtime helpers are kept only for backward compatibility."""

from abc import ABC, abstractmethod
import select
from pathlib import Path
import subprocess
import sys
import warnings


DEPRECATION_MESSAGE = (
    "rpp_orchestrator.script_runtime is deprecated and will be removed in a future release."
)


class ScriptRuntime(ABC):
    @abstractmethod
    def start(self, script_path: Path, *, working_dir: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def debug(self, script_path: Path, *, working_dir: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_running(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_available_output(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def return_code(self) -> int | None:
        raise NotImplementedError


class PythonScriptRuntime(ScriptRuntime):
    def __init__(self) -> None:
        warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        self._process: subprocess.Popen[bytes] | None = None

    def start(self, script_path: Path, *, working_dir: Path) -> None:
        if self.is_running():
            raise RuntimeError("Script runtime is already running.")

        self._process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(working_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    def debug(self, script_path: Path, *, working_dir: Path) -> None:
        if self.is_running():
            raise RuntimeError("Script runtime is already running.")

        self._process = subprocess.Popen(
            [sys.executable, "-m", "pdb", str(script_path)],
            cwd=str(working_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    def stop(self) -> None:
        if not self.is_running():
            self._process = None
            return

        process = self._process
        assert process is not None

        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            process.kill()
        finally:
            self._process = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def read_available_output(self) -> list[str]:
        process = self._process
        if process is None or process.stdout is None:
            return []

        lines: list[str] = []
        while True:
            ready, _, _ = select.select([process.stdout], [], [], 0)
            if not ready:
                break

            line = process.stdout.readline()
            if not line:
                break
            lines.append(line.rstrip("\n"))

        return lines

    def return_code(self) -> int | None:
        if self._process is None:
            return None
        return self._process.poll()


def create_runtime_for_script(script_path: Path) -> ScriptRuntime | None:
    warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return PythonScriptRuntime()
    return None
