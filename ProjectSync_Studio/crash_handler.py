# -*- coding: utf-8 -*-
"""全局崩溃 / 异常捕获

打包后的程序没有控制台，未捕获异常或 Qt 致命错误会直接让窗口消失（"闪退"），
且没有任何痕迹。本模块在程序入口安装全局钩子：

  * sys.excepthook        —— 捕获主线程未捕获异常
  * sys.unraisablehook    —— 捕获 __del__ / 协程等不可raise的异常
  * qInstallMessageHandler —— 捕获 Qt 致命错误（如跨线程访问 QObject）

所有信息落到 %APPDATA%/MediaSync/crash.log，并在 GUI 可用时弹窗显示，
方便用户复现后把日志发回定位根因。
"""
from __future__ import annotations

import sys
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path


def _crash_log_path() -> Path:
    """崩溃日志固定放在用户配置目录下（始终可写）。"""
    try:
        from .constants import CONFIG_DIR
        base = Path(CONFIG_DIR)
    except Exception:
        base = Path(os.environ.get("APPDATA", Path.home())) / "MediaSync"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base / "crash.log"


_LOG_PATH: Path | None = None


def _log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        try:
            _LOG_PATH = _crash_log_path()
        except Exception:
            _LOG_PATH = Path("crash.log")
    return _LOG_PATH


def _write(text: str) -> None:
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _show_box(title: str, detail: str) -> None:
    """GUI 可用时弹窗显示错误，避免用户只看到"闪退"。"""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app is None:
            return
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(
            "程序遇到未捕获的错误，已记录到崩溃日志：\n"
            f"{_log_path()}\n\n可将该文件发回以便定位问题。"
        )
        box.setDetailedText(detail)
        box.setMinimumWidth(600)
        box.exec()
    except Exception:
        pass


_orig_excepthook = sys.excepthook


def _excepthook(exc_type, exc, tb) -> None:
    text = (
        f"[{_timestamp()}] UNCAUGHT [{threading.current_thread().name}] "
        f"{exc_type.__name__}: {exc}\n"
        + "".join(traceback.format_exception(exc_type, exc, tb))
        + "\n"
    )
    _write(text)
    # 仅主线程弹窗（子线程异常交给其调用方处理，避免噪音与重复弹窗）
    if threading.current_thread() is threading.main_thread():
        try:
            _show_box("MediaSync 发生错误", text)
        except Exception:
            pass
    # 仍调用原始 hook，保留原有行为
    try:
        _orig_excepthook(exc_type, exc, tb)
    except Exception:
        pass


def _unraisablehook(args) -> None:
    try:
        text = (
            f"[{_timestamp()}] UNRAISABLE: {args.exc_type.__name__}: {args.exc}\n"
            + "".join(
                traceback.format_exception(
                    args.exc_type, args.exc, args.exc_traceback
                )
            )
            + f"  object={args.object!r}  warnings={args.object.__cause__!r}\n\n"
        )
        _write(text)
    except Exception:
        pass


def _qt_message_handler(msg_type, context, msg) -> None:
    try:
        level = {0: "DEBUG", 1: "WARNING", 2: "ERROR", 3: "FATAL"}.get(
            int(msg_type), str(msg_type)
        )
        text = (
            f"[{_timestamp()}] QT[{level}] {msg}\n"
            f"  ctx={context.file}:{context.line} {context.function}\n\n"
        )
        _write(text)
        if int(msg_type) == 3:  # Qt Fatal
            _show_box("MediaSync 致命错误 (Qt)", text)
    except Exception:
        pass


_installed = False


def install() -> None:
    """安装全局异常 / Qt 消息钩子。应在创建 QApplication 之前调用。

    幂等：可安全被多个入口（run.py / main.py）重复调用，不会重复包装
    导致递归。
    """
    global _orig_excepthook, _installed
    if _installed:
        return
    _installed = True
    _orig_excepthook = sys.excepthook
    sys.excepthook = _excepthook
    sys.unraisablehook = _unraisablehook
    try:
        from PySide6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(_qt_message_handler)
    except Exception:
        pass


def log_exception(msg: str) -> None:
    """供业务代码主动记录一段异常上下文（带完整堆栈）。"""
    _write(f"[{_timestamp()}] LOG {msg}\n" + traceback.format_exc() + "\n")
