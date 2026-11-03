"""Small Qt stand-ins for tests of GUI-adjacent orchestration behaviour.

The helpers are intentionally installed with ``monkeypatch`` before importing
GUI modules.  This lets tests cover application logic without loading Qt's
native platform libraries, while the real GUI remains covered separately by
an environment that provides Qt.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any


class _Signal:
    def connect(self, callback: Any) -> None:
        del callback


class _EnumNamespace:
    def __getattr__(self, name: str) -> int:
        del name
        return 0


class _WidgetMeta(type):
    def __getattr__(cls, name: str) -> _EnumNamespace:
        del cls, name
        return _EnumNamespace()


class FakeWidget(metaclass=_WidgetMeta):
    """Generic widget used only while importing GUI modules under test."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def __enter__(self) -> FakeWidget:
        return self

    def __exit__(self, *args: Any) -> None:
        del args

    def __getattr__(self, name: str) -> Any:
        if name.endswith("Changed") or name in {
            "accepted", "clicked", "rejected", "triggered",
        }:
            return _Signal()

        def no_operation(*args: Any, **kwargs: Any) -> None:
            del args, kwargs

        return no_operation


class FakeTreeWidgetItem:
    def __init__(self, labels: list[str] | None = None) -> None:
        self._labels = labels or []
        self._data: dict[tuple[int, object], Any] = {}
        self._children: list[FakeTreeWidgetItem] = []
        self._parent: FakeTreeWidgetItem | None = None

    def addChild(self, item: FakeTreeWidgetItem) -> None:
        item._parent = self
        self._children.append(item)

    def child(self, index: int) -> FakeTreeWidgetItem:
        return self._children[index]

    def childCount(self) -> int:
        return len(self._children)

    def data(self, column: int, role: object) -> Any:
        return self._data.get((column, role))

    def parent(self) -> FakeTreeWidgetItem | None:
        return self._parent

    def setData(self, column: int, role: object, value: Any) -> None:
        self._data[(column, role)] = value

    def setExpanded(self, expanded: bool) -> None:
        del expanded

    def setFirstColumnSpanned(self, spanned: bool) -> None:
        del spanned

    def text(self, index: int) -> str:
        return self._labels[index]


class FakeTreeWidget:
    def __init__(self) -> None:
        self._items: list[FakeTreeWidgetItem] = []
        self._current_item: FakeTreeWidgetItem | None = None

    def addTopLevelItem(self, item: FakeTreeWidgetItem) -> None:
        self._items.append(item)

    def clear(self) -> None:
        self._items = []
        self._current_item = None

    def currentItem(self) -> FakeTreeWidgetItem | None:
        return self._current_item

    def setCurrentItem(self, item: FakeTreeWidgetItem | None) -> None:
        self._current_item = item

    def topLevelItem(self, index: int) -> FakeTreeWidgetItem:
        return self._items[index]


class FakeControl:
    def __init__(self) -> None:
        self.enabled = False
        self.visible = False

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setVisible(self, visible: bool) -> None:
        self.visible = visible


class FakeLog:
    def appendPlainText(self, text: str) -> None:
        del text


class FakeApplication:
    _instance: FakeApplication | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        type(self)._instance = self

    @classmethod
    def instance(cls) -> FakeApplication | None:
        return cls._instance

    def processEvents(self) -> None:
        return None


class FakeMessageBox:
    StandardButton = SimpleNamespace(Yes=1, No=2, Ok=3, Cancel=4)

    @staticmethod
    def critical(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    @staticmethod
    def information(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    @staticmethod
    def question(*args: Any, **kwargs: Any) -> int:
        del args, kwargs
        return FakeMessageBox.StandardButton.No

    @staticmethod
    def warning(*args: Any, **kwargs: Any) -> None:
        del args, kwargs


class FakeQt:
    ItemDataRole = SimpleNamespace(UserRole="user-role")


def _fallback_widget(name: str) -> type[FakeWidget]:
    del name
    return FakeWidget


def install_fake_qt(monkeypatch: Any) -> SimpleNamespace:
    """Install fake ``PyQt6`` modules and return their useful test doubles."""
    for module_name in tuple(sys.modules):
        if module_name == "rpp_orchestrator.gui" or module_name.startswith(
                "rpp_orchestrator.gui."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    pyqt6 = ModuleType("PyQt6")
    qtcore = ModuleType("PyQt6.QtCore")
    qtgui = ModuleType("PyQt6.QtGui")
    qtwidgets = ModuleType("PyQt6.QtWidgets")

    qtcore.Qt = FakeQt
    qtcore.QSignalBlocker = FakeWidget
    qtcore.QTimer = FakeWidget
    qtcore.__getattr__ = _fallback_widget

    qtgui.QAction = FakeWidget
    qtgui.QColor = FakeWidget
    qtgui.QPalette = FakeWidget
    qtgui.__getattr__ = _fallback_widget

    qtwidgets.QApplication = FakeApplication
    qtwidgets.QMessageBox = FakeMessageBox
    qtwidgets.QTreeWidget = FakeTreeWidget
    qtwidgets.QTreeWidgetItem = FakeTreeWidgetItem
    qtwidgets.__getattr__ = _fallback_widget

    pyqt6.QtCore = qtcore
    pyqt6.QtGui = qtgui
    pyqt6.QtWidgets = qtwidgets

    monkeypatch.setitem(sys.modules, "PyQt6", pyqt6)
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PyQt6.QtGui", qtgui)
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", qtwidgets)

    return SimpleNamespace(
        Application=FakeApplication,
        Control=FakeControl,
        Log=FakeLog,
        MessageBox=FakeMessageBox,
        Qt=FakeQt,
        TreeWidget=FakeTreeWidget,
        TreeWidgetItem=FakeTreeWidgetItem,
    )
