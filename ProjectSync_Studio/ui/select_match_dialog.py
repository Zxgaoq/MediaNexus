# -*- coding: utf-8 -*-
"""重新匹配项目文件夹选择对话框"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QMessageBox,
)

from ..config_manager import config_manager


class SelectMatchDialog(QDialog):
    """列出匹配候选文件夹，用户选择并确认。"""

    matched_changed = Signal()

    def __init__(self, project: dict, candidates: list[dict], parent=None):
        super().__init__(parent)
        self._project = project
        self._candidates = candidates
        self.setWindowTitle("重新匹配 — 选择项目文件夹")
        self.setMinimumSize(600, 400)
        self._init_ui()
        self._populate()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        name = self._project.get("name") or ""
        confirmed = self._project.get("confirmed_nas_path", "")
        info = QLabel(f"项目：{name}\n当前：{confirmed or '（未确认）'}")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.confirm_btn = QPushButton("确认为此项目")
        self.confirm_btn.setObjectName("primary")
        self.confirm_btn.clicked.connect(self._confirm)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(self.confirm_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _populate(self):
        for c in self._candidates:
            text = f"{c['name']}  ({c['score']}%)  [{c['strategy']}]  — {c['path']}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, c["path"])
            item.setToolTip(c["path"])
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _confirm(self):
        sel = self.list_widget.currentItem()
        if not sel:
            QMessageBox.warning(self, "提示", "请先选择一个匹配项")
            return
        path = sel.data(Qt.ItemDataRole.UserRole)
        name = self._project.get("local_name", "")
        config_manager.set_confirmed_nas(name, path)
        self.matched_changed.emit()
        self.accept()
