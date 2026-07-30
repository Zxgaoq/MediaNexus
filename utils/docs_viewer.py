# -*- coding: utf-8 -*-
"""
内嵌用户手册查看器（网页形式）。

优先使用 Qt WebEngine（QWebEngineView）以「网页」方式渲染 docs/MediaSync-Manual.html；
若运行环境未带 WebEngine（极少数精简安装），自动回退到 QTextBrowser 渲染同一份 HTML。
两种方式都是「在应用窗口内嵌入网页」，不会跳转到外部浏览器 / 记事本。
"""
import os
import sys

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser


MANUAL_FILENAME = "MediaSync-Manual.html"


def _find_manual_html():
    """定位内嵌手册 HTML（兼容开发态与 PyInstaller 打包态）。"""
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "docs"))
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "_internal", "docs"))
        candidates.append(os.path.join(exe_dir, "docs"))
    # 开发态：utils/ 的上一级即项目根
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(here, "docs"))
    candidates.append(os.path.join(here, "..", "docs"))
    for d in candidates:
        p = os.path.join(d, MANUAL_FILENAME)
        if os.path.isfile(p):
            return os.path.abspath(p)
    return None


def open_manual(parent=None):
    """打开内嵌用户手册（网页）。返回已 show() 的 QDialog 实例。"""
    path = _find_manual_html()
    dlg = QDialog(parent)
    dlg.setWindowTitle("MediaSync 用户手册")
    dlg.resize(980, 720)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)

    if path is None:
        tb = QTextBrowser(dlg)
        tb.setHtml(
            "<h2>用户手册未找到</h2>"
            "<p>未找到 %s，请确认 docs 目录已随程序一同分发。</p>" % MANUAL_FILENAME
        )
        layout.addWidget(tb)
        dlg.show()
        return dlg

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView(dlg)
        view.load(QUrl.fromLocalFile(path))
        layout.addWidget(view)
    except Exception:
        # 回退：QTextBrowser 也能渲染这份自包含 HTML
        tb = QTextBrowser(dlg)
        tb.setSource(QUrl.fromLocalFile(path))
        layout.addWidget(tb)

    dlg.show()
    return dlg
