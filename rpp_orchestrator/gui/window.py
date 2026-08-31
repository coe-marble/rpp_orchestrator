from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, QSettings, Qt
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
    QListWidget,
    QListWidgetItem,
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
    MAX_RECENT_LIBRARIES = 10
    RECENT_LIBRARIES_KEY = "recentLibraries"
    _open_windows: list[WorkspaceWindow] = []

    def __init__(self):
        super().__init__()
        self.workspace: Workspace | None = None
        self.settings = QSettings("RPP", "rpp_orchestrator")
        self.recent_libraries = self._load_recent_libraries()
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
        self._build_file_menu()

    def _build_file_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")

        open_action = file_menu.addAction("Open…")
        open_action.triggered.connect(
            lambda _checked=False: self.open_workspace()
        )
        open_new_action = file_menu.addAction("Open in New Window…")
        open_new_action.triggered.connect(
            lambda _checked=False: self.open_workspace(in_new_window=True)
        )

        file_menu.addSeparator()
        self.recent_libraries_menu = file_menu.addMenu("Recently Opened")
        self._refresh_recent_libraries_menu()

    def _load_recent_libraries(self) -> list[Path]:
        saved_paths = self.settings.value(self.RECENT_LIBRARIES_KEY, []) or []
        if isinstance(saved_paths, str):
            saved_paths = [saved_paths]

        recent_libraries: list[Path] = []
        for saved_path in saved_paths:
            path = Path(saved_path).expanduser()
            if path.is_dir() and path not in recent_libraries:
                recent_libraries.append(path)

        self.settings.setValue(
            self.RECENT_LIBRARIES_KEY,
            [str(path) for path in recent_libraries],
        )
        return recent_libraries

    def _remember_library(self, path: Path) -> None:
        path = path.expanduser().resolve()
        self.recent_libraries = [
            recent_path
            for recent_path in self.recent_libraries
            if recent_path != path and recent_path.is_dir()
        ]
        self.recent_libraries.insert(0, path)
        self.recent_libraries = self.recent_libraries[
            :self.MAX_RECENT_LIBRARIES
        ]
        self.settings.setValue(
            self.RECENT_LIBRARIES_KEY,
            [str(recent_path) for recent_path in self.recent_libraries],
        )
        self._refresh_recent_library_views()

    def _forget_library(self, path: Path) -> None:
        self.recent_libraries = [
            recent_path for recent_path in self.recent_libraries
            if recent_path != path
        ]
        self.settings.setValue(
            self.RECENT_LIBRARIES_KEY,
            [str(recent_path) for recent_path in self.recent_libraries],
        )
        self._refresh_recent_library_views()

    @staticmethod
    def _recent_library_label(path: Path) -> str:
        return f"{path.name} — {path}"

    def _refresh_recent_library_views(self) -> None:
        self._refresh_recent_libraries_menu()
        self._refresh_recent_libraries_list()

    def _refresh_recent_libraries_menu(self) -> None:
        self.recent_libraries_menu.clear()
        if not self.recent_libraries:
            empty_action = self.recent_libraries_menu.addAction("No Recent Libraries")
            empty_action.setEnabled(False)
            return

        for path in self.recent_libraries:
            library_menu = self.recent_libraries_menu.addMenu(
                self._recent_library_label(path)
            )
            open_action = library_menu.addAction("Open")
            open_action.triggered.connect(
                lambda _checked=False, selected_path=path:
                    self._open_workspace_path(selected_path)
            )
            open_new_action = library_menu.addAction("Open in New Window")
            open_new_action.triggered.connect(
                lambda _checked=False, selected_path=path:
                    self._open_workspace_path(
                        selected_path, in_new_window=True
                    )
            )

    def _refresh_recent_libraries_list(self) -> None:
        self.recent_libraries_list.clear()
        for path in self.recent_libraries:
            item = QListWidgetItem(self._recent_library_label(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setSizeHint(QSize(0, 36))
            self.recent_libraries_list.addItem(item)

    def _open_recent_library_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._open_workspace_path(Path(path))

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

        recent_label = QLabel("Recently Opened", card)
        self.recent_libraries_list = QListWidget(card)
        self.recent_libraries_list.setMaximumHeight(180)
        self.recent_libraries_list.setSpacing(4)
        self.recent_libraries_list.setWordWrap(False)
        self.recent_libraries_list.itemDoubleClicked.connect(
            self._open_recent_library_item
        )
        self._refresh_recent_libraries_list()

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
        card_layout.addWidget(recent_label)
        card_layout.addWidget(self.recent_libraries_list)
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

    def open_workspace(self, in_new_window: bool = False) -> None:
        root = QFileDialog.getExistingDirectory(self, "Open workspace")
        if not root:
            return

        path = Path(root).expanduser().resolve()
        self._open_workspace_path(path, in_new_window=in_new_window)

    def _open_workspace_path(
        self, path: Path, in_new_window: bool = False
    ) -> None:
        path = path.expanduser().resolve()
        if not path.is_dir():
            self._forget_library(path)
            QMessageBox.warning(
                self,
                "Missing Library",
                f"The library path '{path}' no longer exists.",
            )
            return

        lm = self.editor.lib_manager
        if not lm.is_valid_plugin_library(path):
            QMessageBox.warning(self,
                "Invalid Workspace",
                f"The selected path '{path}' is not a valid RPP plugin library.")
            return

        self._remember_library(path)
        if in_new_window:
            window = WorkspaceWindow()
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            workspace = Workspace(root=path,
                lib_manager=window.editor.lib_manager)
            workspace.ensure_layout()
            window.set_workspace(workspace)
            window.show()
            WorkspaceWindow._open_windows.append(window)
            window.destroyed.connect(
                lambda _object=None, child=window:
                    self._remove_open_window(child)
            )
            return

        workspace = Workspace(root=path, lib_manager=self.editor.lib_manager)
        workspace.ensure_layout()
        self.set_workspace(workspace)

    @classmethod
    def _remove_open_window(cls, window: WorkspaceWindow) -> None:
        if window in cls._open_windows:
            cls._open_windows.remove(window)

    def set_workspace(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self._remember_library(workspace.root)
        self.editor.set_workspace(workspace)
        self.stack.setCurrentWidget(self.editor)
        self._expand_for_workspace()
        self.setWindowTitle(f"RPP Workspace - {workspace.root}")
