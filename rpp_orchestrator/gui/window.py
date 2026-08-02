from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from rpp_plugin_registrator.library_manager import LibraryManager

from ..workspace import Workspace, create_workspace
from .editor import WorkspaceEditor


class NewWorkspaceDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, lib_manager=None):
        super().__init__(parent)

        if lib_manager is None:
            self.lib_manager = LibraryManager()
        else:
            self.lib_manager = lib_manager

        self.setWindowTitle("New Workspace")
        self.setMinimumSize(400, 200)
        self.name_label = QLabel("Workspace Name:", self)
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Enter workspace name")
        self.path_label = QLabel("Workspace Path:", self)
        self.path_input = QLineEdit(self)
        self.path_input.setPlaceholderText("Select workspace path")
        self.browse_button = QPushButton("Browse", self)
        self.browse_button.clicked.connect(self.browse_folder)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        self.create_button = QPushButton("Create", self)
        self.create_button.clicked.connect(self.accept)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.name_input)
        self.layout.addWidget(self.path_label)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_button)
        self.layout.addLayout(path_layout)
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.create_button)
        self.layout.addLayout(button_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Workspace Path")
        if folder:
            self.path_input.setText(folder)

    def get_selected_folder(self) -> str:
        return self.path_input.text()

    def get_workspace_name(self) -> str:
        return self.name_input.toPlainText().strip()

    def accept(self) -> None:
        name = self.get_workspace_name()
        path = self.get_selected_folder()

        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid workspace name.")
            return

        if not path:
            QMessageBox.warning(self, "Invalid Path", "Please select a valid workspace path.")
            return

        workspace_root = Path(path).expanduser() / name
        if workspace_root.exists():
            reply = QMessageBox.question(
                self,
                "Overwrite Workspace",
                f"The workspace '{name}' already exists at the selected path. Do you want to overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        super().accept()

    def reject(self) -> None:
        super().reject()

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

        root = QFileDialog.getExistingDirectory(self, "New workspace")
        lm = self.editor.lib_manager
        path = Path(root).expanduser().resolve()
        if not lm.is_valid_plugin_library(path):
            QMessageBox.warning(self,
                "Invalid Workspace",
                f"The selected path '{root}' is not a valid RPP plugin library.")
            return


        if Workspace.workspace_exists(path):
            reply = QMessageBox.question(
                self,
                "Overwrite Workspace",
                "A workspace already exists at the selected path. Do you want to overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        name = lm.lib_name_from_path(path)
        workspace_root = path / name.strip()

        workspace = create_workspace(workspace_root,
            name=name.strip(), overwrite=True, lib_manager=self.editor.lib_manager)
        workspace.ensure_layout()
        self.set_workspace(workspace)

    def open_workspace(self) -> None:
        root = QFileDialog.getExistingDirectory(self, "Open workspace")
        if not root:
            return

        lm = self.editor.lib_manager
        path = Path(root).expanduser().resolve()
        if not lm.is_valid_plugin_library(path):
            QMessageBox.warning(self,
                "Invalid Workspace",
                f"The selected path '{root}' is not a valid RPP plugin library.")
            return

        workspace = Workspace(root=Path(root).expanduser().resolve(),
            lib_manager=self.editor.lib_manager)
        workspace.ensure_layout()
        self.set_workspace(workspace)

    def set_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.editor.set_workspace(workspace)
        self.stack.setCurrentWidget(self.editor)
        self._expand_for_workspace()
        self.setWindowTitle(f"RPP Workspace - {workspace.root}")
