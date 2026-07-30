# -*- coding: utf-8 -*-
"""
ProjectSync Studio - 通用小组件
  * SpinnerLabel：纯文本旋转加载动画（无外部图片依赖），用于 NAS 访问等待。
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QWidget


class SpinnerLabel(QLabel):
    """轻量加载动画：在「| / - \\」之间循环，配合文字提示。"""

    _FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._idx = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._base = "加载中"
        self.setText(self._base)

    def _tick(self):
        self._idx = (self._idx + 1) % len(self._FRAMES)
        self.setText(f"{self._base}  {self._FRAMES[self._idx]}")

    def start(self, text: str = "加载中"):
        self._base = text
        self.setText(f"{text}  {self._FRAMES[0]}")
        if not self._timer.isActive():
            self._timer.start(120)

    def stop(self):
        self._timer.stop()
        self.setText("")
