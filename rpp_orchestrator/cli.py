from __future__ import annotations

import argparse
from pathlib import Path

from .gui import main as gui_main
from .workspace import create_workspace


def command_create(args) -> int:
    root = Path(args.root).expanduser().resolve() / args.name
    create_workspace(root, name=args.name, overwrite=args.overwrite)
    print(f"Created workspace: {root}")
    return 0


def command_gui(args) -> int:
    workspace_root = getattr(args, "root", None)
    if workspace_root:
        return gui_main(Path(workspace_root).expanduser().resolve())
    return gui_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rpp ws", description="RPP workspace tools")
    parser.add_argument(
        "--root",
        default=None,
        help="workspace folder to open in the GUI",
    )
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="create a new workspace")
    create_parser.add_argument("name", help="workspace name")
    create_parser.add_argument("root", help="root directory where the workspace folder will be created")
    create_parser.add_argument("--metadata", default=None, help="workspace metadata as JSON")
    create_parser.add_argument("--overwrite", action="store_true", help="overwrite an existing empty root")
    create_parser.set_defaults(func=command_create)

    parser.set_defaults(func=command_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    return int(result or 0)
