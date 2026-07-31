# -*- coding: utf-8 -*-
"""应用内文件剪贴板（复制 / 剪切 / 粘贴）。

与系统剪贴板互操作：
  * 复制 / 剪切时，把选中的文件 URL 写入系统剪贴板（CF_HDROP），
    这样在资源管理器里也能直接 Ctrl+V 粘贴。
  * 粘贴时若应用内剪贴板为空，则回退读取系统剪贴板里的文件
    （支持从资源管理器复制后在本软件内粘贴）。

剪切（cut）在粘贴后会被消费（清空）；复制（copy）则保留，可多次粘贴。
"""
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QApplication


class FileClipboard:
    def __init__(self):
        self._operation: str | None = None   # 'copy' | 'cut'
        self._paths: List[str] = []

    @property
    def has_content(self) -> bool:
        return bool(self._paths)

    def is_cut(self) -> bool:
        return self._operation == "cut"

    def get(self) -> List[str]:
        return list(self._paths)

    def set(self, paths: List[str], operation: str) -> None:
        self._operation = operation if operation in ("copy", "cut") else "copy"
        self._paths = [p for p in (paths or []) if p]
        self._sync_to_system()

    def clear(self) -> None:
        self._operation = None
        self._paths = []
        self._clear_system()

    def consume(self) -> List[str]:
        """取出路径；若是剪切则一并清空。"""
        paths = self.get()
        if self.is_cut():
            self.clear()
        return paths

    # ---- 系统剪贴板互操作 ----
    @staticmethod
    def _clipboard():
        app = QApplication.instance()
        return app.clipboard() if app is not None else None

    def _sync_to_system(self) -> None:
        cb = self._clipboard()
        if cb is None:
            return
        try:
            mime = QMimeData()
            urls = [QUrl.fromLocalFile(p) for p in self._paths if os.path.exists(p)]
            mime.setUrls(urls)
            cb.setMimeData(mime)
        except Exception:  # noqa: BLE001
            pass

    def _clear_system(self) -> None:
        cb = self._clipboard()
        if cb is None:
            return
        try:
            if cb.mimeData().hasUrls():
                cb.clear()
        except Exception:  # noqa: BLE001
            pass

    def read_system_files(self) -> List[str]:
        """从系统剪贴板读取文件（资源管理器复制的文件）。"""
        cb = self._clipboard()
        if cb is None:
            return []
        try:
            mime = cb.mimeData()
            if mime and mime.hasUrls():
                return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        except Exception:  # noqa: BLE001
            pass
        return []


# 全局单例
file_clipboard = FileClipboard()
