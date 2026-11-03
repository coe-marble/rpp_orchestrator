from typing import Any


__all__ = ["main"]


def main(*args: Any, **kwargs: Any) -> int:
    # Do not import the Qt application module when this package is inspected
    # by a non-GUI command.  Qt is required only when the GUI is launched.
    from .main import main as gui_main

    return gui_main(*args, **kwargs)
