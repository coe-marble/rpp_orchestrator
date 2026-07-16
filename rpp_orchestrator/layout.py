from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True)
class WorkspaceLayout:
    manifest_file: str = "rpp_workspace.json"
    plugin_dir: str = "plugins"
    params_dir: str = "params"
    scripts_dir: str = "scripts"
    scenarios_dir: str = "scenarios"
    data_dir: str = "data"
    builds_dir: str = "builds"
    logs_dir: str = "logs"

    def directories(self) -> Tuple[str, ...]:
        return (
            self.plugin_dir,
            self.params_dir,
            self.scripts_dir,
            self.scenarios_dir,
            self.data_dir,
            self.builds_dir,
            self.logs_dir,
        )


@dataclass(frozen=True)
class ComponentLayout:
    data_dir: str = "data"
    params_dir: str = "params"
    subcomponents_dir: str = "subcomponents"
    description_filename: str = "description.json"
    callbacks_filename: str = "callbacks.py"
    parameters_filename: str = "parameters.py"


def default_component_layout() -> ComponentLayout:
    return ComponentLayout()


def default_layout() -> WorkspaceLayout:
    return WorkspaceLayout()


def workspace_paths(root: Path, layout: WorkspaceLayout) -> dict[str, Path]:
    return {
        "root": root,
        "manifest": root / layout.manifest_file,
        "scripts": root / layout.scripts_dir,
        "parts": root / layout.data_dir,
        "builds": root / layout.builds_dir,
        "logs": root / layout.logs_dir,
    }
