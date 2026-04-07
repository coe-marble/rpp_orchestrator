from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from ..workspace import Workspace
from .window import WorkspaceWindow


def main(workspace_root: Path | None = None) -> int:
    app = QApplication(sys.argv)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f3f5f7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#19202a"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#19202a"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#19202a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QMainWindow { background: #f3f5f7; }
        QMenuBar { background: #ffffff; border-bottom: 1px solid #d9dee6; }
        QListWidget {
            background: #ffffff;
            border: 1px solid #d9dee6;
            border-radius: 10px;
            padding: 6px;
        }
        QListWidget::item {
            padding: 8px;
            border-radius: 6px;
        }
        QListWidget::item:selected {
            background: #0b6ef9;
            color: #ffffff;
        }
        QPushButton {
            background: #ffffff;
            border: 1px solid #cfd7e3;
            border-radius: 8px;
            padding: 8px 12px;
            font-weight: 600;
        }
        QPushButton:hover { border-color: #0b6ef9; }
        QPushButton:disabled { color: #8893a3; }
        #helpLabel { color: #556274; }
        #emptyCard {
            background: #ffffff;
            border: 1px solid #d9dee6;
            border-radius: 14px;
        }
        #emptyTitle {
            font-size: 22px;
            font-weight: 700;
            color: #19202a;
        }
        #emptySubtitle {
            color: #4d5a6b;
            font-size: 13px;
        }
        """
    )

    window = WorkspaceWindow()
    if workspace_root is not None:
        workspace = Workspace(root=Path(workspace_root).expanduser().resolve())
        workspace.ensure_layout()
        window.set_workspace(workspace)
    window.show()
    return app.exec()
