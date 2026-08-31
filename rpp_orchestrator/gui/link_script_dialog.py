from __future__ import annotations

from collections import defaultdict

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..script_catalog import RegisteredScript


class LinkScriptDialog(QDialog):
    def __init__(
        self,
        scripts: list[RegisteredScript],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Link Registered Script")
        self.setMinimumSize(480, 360)
        self._selected_script: RegisteredScript | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a script from another registered library:"))

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Script", "Language"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self._update_button_state)
        self.tree.itemDoubleClicked.connect(self._accept_item)
        layout.addWidget(self.tree)

        grouped_scripts: dict[str, list[RegisteredScript]] = defaultdict(list)
        for script in scripts:
            grouped_scripts[script.library].append(script)
        for library_name in sorted(grouped_scripts):
            library_item = QTreeWidgetItem([library_name])
            self.tree.addTopLevelItem(library_item)
            for script in grouped_scripts[library_name]:
                script_item = QTreeWidgetItem([script.name, script.language])
                script_item.setData(0, Qt.ItemDataRole.UserRole, script)
                library_item.addChild(script_item)
            library_item.setExpanded(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self.ok_button is not None:
            self.ok_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_script(self) -> RegisteredScript | None:
        return self._selected_script

    def accept(self) -> None:
        item = self.tree.currentItem()
        script = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(script, RegisteredScript):
            return
        self._selected_script = script
        super().accept()

    def _update_button_state(self) -> None:
        item = self.tree.currentItem()
        script = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if self.ok_button is not None:
            self.ok_button.setEnabled(isinstance(script, RegisteredScript))

    def _accept_item(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        self.tree.setCurrentItem(item)
        self.accept()
