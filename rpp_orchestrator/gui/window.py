from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from ..workspace import Workspace, create_workspace
from .editor import WorkspaceEditor


class WorkspaceWindow(QMainWindow):
    COMPACT_SIZE = (620, 440)
    WORKSPACE_SIZE = (980, 640)

    def __init__(self):
        super().__init__()
        self.workspace: Workspace | None = None
        self.setWindowTitle("RPP Workspace")
        self.setMinimumSize(*self.COMPACT_SIZE)
        self.resize(*self.COMPACT_SIZE)

        self.stack = QStackedWidget(self)
        self.editor = WorkspaceEditor(self)
        self.empty_state = self._build_empty_state()
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.editor)
        self.setCentralWidget(self.stack)
        self.stack.setCurrentWidget(self.empty_state)

    def _expand_for_workspace(self) -> None:
        self.setMinimumSize(*self.WORKSPACE_SIZE)
        self.resize(
            max(self.width(), self.WORKSPACE_SIZE[0]),
            max(self.height(), self.WORKSPACE_SIZE[1]),
        )

    def _build_empty_state(self) -> QWidget:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(16)

        card = QFrame(root)
        card.setObjectName("emptyCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(12)

        title = QLabel("RPP Workspace", card)
        title.setObjectName("emptyTitle")
        subtitle = QLabel("Create a workspace or open an existing one to manage orchestration scripts.", card)
        subtitle.setWordWrap(True)
        subtitle.setObjectName("emptySubtitle")

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 8, 0, 0)
        actions_layout.setSpacing(10)

        new_btn = QPushButton("New Workspace", actions)
        new_btn.clicked.connect(self.new_workspace)
        open_btn = QPushButton("Open Workspace", actions)
        open_btn.clicked.connect(self.open_workspace)
        actions_layout.addWidget(new_btn)
        actions_layout.addWidget(open_btn)
        actions_layout.addStretch(1)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addWidget(actions)

        layout.addStretch(1)
        layout.addWidget(card)
        layout.addStretch(2)
        return root

    def new_workspace(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "Select workspace root")
        if not root:
            return
        name, accepted = QInputDialog.getText(self, "New Workspace", "Workspace name")
        if not accepted or not name.strip():
            return
        workspace_root = Path(root).expanduser() / name.strip()
        workspace = create_workspace(workspace_root, name=name.strip(), overwrite=False)
        self.set_workspace(workspace)

    def open_workspace(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "Open workspace")
        if not root:
            return
        workspace = Workspace(root=__import__("pathlib").Path(root).expanduser().resolve())
        workspace.ensure_layout()
        self.set_workspace(workspace)

    def set_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.editor.set_workspace(workspace)
        self.stack.setCurrentWidget(self.editor)
        self._expand_for_workspace()
        self.setWindowTitle(f"RPP Workspace - {workspace.root}")
