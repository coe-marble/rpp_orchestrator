from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QCheckBox,
    QPushButton, QHBoxLayout, QWidget, QDialogButtonBox, QFileDialog
)
from PyQt6 import QtCore

class NewScriptDialog(QDialog):
    def __init__(self, parent=None, title="Enter values"):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle(title)
        layout = QFormLayout(self)
        self.le = QLineEdit(self)
        self.le.setMinimumWidth(300)
        layout.addRow("Name", self.le)
        self.browse_btn = QPushButton("Browse", self)
        self.browse_btn.clicked.connect(self.on_browse)
        hlayout = QHBoxLayout()
        self.path_line_edit = QLineEdit(self)
        hlayout.addWidget(self.path_line_edit)
        hlayout.addWidget(self.browse_btn)
        self.script_path_w = QWidget(self)
        self.script_path_w.setLayout(hlayout)
        layout.addRow("Path", self.script_path_w)
        layout.labelForField(self.script_path_w).setVisible(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.layout = layout
        self.name = None
        self.path = None

    def accept(self):
        name = self.le.text()
        path = self.script_path_w.layout().itemAt(0).widget().text() if self.script_path_w.layout().count() > 0 else None
        if name is None or name.strip() == "":
            self.parent.log_message("Invalid library name.")
            return
        self.name = name.strip()
        self.path = path.strip()
        return super().accept()

    def on_browse(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Link Directory", "")
        if dir_path:
            self.path_line_edit.setText(dir_path)

    