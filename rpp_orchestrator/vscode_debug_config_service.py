from __future__ import annotations

"""Deprecated: VS Code debug config helper is kept only for backward compatibility."""

from dataclasses import dataclass
import shutil
import subprocess
from pathlib import Path
import json
from typing import Any
import warnings


DEPRECATION_MESSAGE = (
    "rpp_orchestrator.vscode_debug_config_service is deprecated and will be removed in a future release."
)


@dataclass(frozen=True)
class EnsureDebugConfigResult:
    status: str
    config_name: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class LaunchDebugResult:
    status: str
    message: str | None = None


class VscodeDebugConfigService:
    def __init__(self) -> None:
        warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)

    def ensure_for_script(self, script_path: Path, workspace_root: Path) -> EnsureDebugConfigResult:
        config = self._build_debug_configuration(script_path, workspace_root)
        if config is None:
            return EnsureDebugConfigResult(
                status="unsupported",
                message=f"No VS Code debug configuration template is available for {script_path.suffix or 'this file type'}.",
            )

        vscode_dir = workspace_root / ".vscode"
        launch_path = vscode_dir / "launch.json"

        payload: dict[str, Any] = {"version": "0.2.0", "configurations": []}
        if launch_path.exists():
            try:
                raw_payload = json.loads(launch_path.read_text(encoding="utf-8"))
                if isinstance(raw_payload, dict):
                    payload = raw_payload
            except Exception:
                return EnsureDebugConfigResult(
                    status="invalid",
                    message="Existing .vscode/launch.json is invalid JSON; preserving it unchanged.",
                )

        configurations = payload.get("configurations")
        if not isinstance(configurations, list):
            configurations = []
            payload["configurations"] = configurations

        config_name = str(config.get("name") or "")
        if any(isinstance(item, dict) and str(item.get("name") or "") == config_name for item in configurations):
            return EnsureDebugConfigResult(status="exists", config_name=config_name)

        configurations.append(config)
        payload.setdefault("version", "0.2.0")

        vscode_dir.mkdir(parents=True, exist_ok=True)
        launch_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        return EnsureDebugConfigResult(
            status="created",
            config_name=config_name,
            message=f"Created VS Code debug configuration: {config_name}",
        )

    def _build_debug_configuration(self, script_path: Path, workspace_root: Path) -> dict[str, Any] | None:
        suffix = script_path.suffix.lower()
        if suffix == ".py":
            relative_program = self._workspace_folder_relative_expression(script_path, workspace_root)
            return {
                "name": f"Debug Script: {script_path.name}",
                "type": "debugpy",
                "request": "launch",
                "program": relative_program,
                "cwd": "${workspaceFolder}",
                "console": "integratedTerminal",
                "justMyCode": False,
            }

        return None

    def _workspace_folder_relative_expression(self, path: Path, workspace_root: Path) -> str:
        try:
            relative = path.resolve().relative_to(workspace_root.resolve())
            return "${workspaceFolder}/" + relative.as_posix()
        except Exception:
            return str(path)

    def launch_debug_for_script(self, script_path: Path, workspace_root: Path) -> LaunchDebugResult:
        code_cmd = shutil.which("code")
        if not code_cmd:
            return LaunchDebugResult(status="missing-code", message="VS Code CLI 'code' was not found in PATH.")

        try:
            subprocess.Popen([code_cmd, "-r", str(workspace_root), "-g", f"{script_path}:1"])
        except Exception as exc:
            return LaunchDebugResult(status="open-failed", message=f"Failed to open script in VS Code: {exc}")

        xdg_open = shutil.which("xdg-open")
        if not xdg_open:
            return LaunchDebugResult(
                status="missing-xdg-open",
                message="xdg-open was not found. Cannot trigger VS Code debug command URI.",
            )

        try:
            subprocess.Popen([xdg_open, "vscode://command/workbench.action.debug.start"])
        except Exception as exc:
            return LaunchDebugResult(status="debug-start-failed", message=f"Failed to trigger VS Code debug start: {exc}")

        return LaunchDebugResult(status="ok", message=f"Started VS Code debug for {script_path.name}.")
