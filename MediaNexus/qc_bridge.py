# -*- coding: utf-8 -*-
"""
QC 检测桥接模块
==============
负责从 MediaNexus 打开 QC 检测窗口 / 多版本对比窗口，提供统一的入口函数。
"""

import os
import multiprocessing

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QProgressDialog,
)

from qc_gui.main_window import MainWindow as QCMainWindow
from qc_gui.multi_version_compare_dialog import MultiVersionCompareDialog
from utils.ffmpeg_manager import FFmpegManager

# ── 全局窗口引用（防止被 GC 回收） ──
_open_qc_windows: list = []
_open_compare_dialogs: list = []


def _cpu_half() -> int:
    """右键启动默认线程数 = CPU 总逻辑核心数的一半（至少 1）。"""
    return max(1, multiprocessing.cpu_count() // 2)


def open_qc_detection(file_paths: list[str] | None = None,
                      thread_count: int | None = None):
    """
    打开 QC 检测窗口（独立顶级窗口，非模态）。

    参数
    ----
    file_paths: 要预载入检测列表的视频文件路径列表（可空）。
    thread_count: 检测并发线程数；为 None 则用默认值 _cpu_half()。
    """
    if thread_count is None:
        thread_count = _cpu_half()

    # ── FFmpeg 可用性守卫：缺失时引导下载，避免质检直接崩 ──
    mgr = FFmpegManager()
    if not mgr.is_available:
        ans = QMessageBox.question(
            None, "需要 FFmpeg",
            "视频质检功能依赖 FFmpeg，当前未找到。\n是否现在下载？\n"
            "（也可在「设置 → 组件」中手动指定已安装的 FFmpeg 目录）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return None
        dlg = QProgressDialog("正在获取 FFmpeg…", "取消", 0, 100, None)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        def _cb(frac, status):
            dlg.setValue(int(frac * 100))
            dlg.setLabelText(status)
            QApplication.processEvents()
            return not dlg.wasCanceled()

        ok, msg = mgr.ensure_ffmpeg(progress_cb=_cb)
        dlg.close()
        if not ok:
            QMessageBox.warning(
                None, "未能获取 FFmpeg",
                f"{msg}\n\n请在「设置 → 组件」中手动指定 FFmpeg 目录后再试。",
            )
            return None

    win = QCMainWindow()
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    win.bottom_bar.thread_spin.setValue(thread_count)

    win.setWindowTitle("影枢 QC")

    # QC 配置已统一由主程序配置单例（%APPDATA% 下的 qc_presets /
    # qc_active_preset / qc_settings）管理，VideoQC 启动时会直接读取，
    # 无需在此重复注入。

    if file_paths:
        validated = [os.path.normpath(p) for p in file_paths if os.path.isfile(p)]
        if validated:
            win._add_paths(validated)

    win.show()
    _open_qc_windows.append(win)

    # 右键入口：自动开始检测（工具栏入口不会预载文件，_start_detection 会跳过空列表）
    if file_paths and validated:
        win._start_detection()

    # 窗口关闭时从列表中移除，避免悬挂引用
    win.destroyed.connect(lambda: _cleanup_ref(win, _open_qc_windows))
    return win


def open_multi_version_compare(folder_paths: list[str] | None = None):
    """
    打开多版本对比窗口（独立顶级窗口，非模态）。

    参数
    ----
    folder_paths: 要预载入对比的文件夹路径列表（至少需要 2 个）。
    """
    dlg = MultiVersionCompareDialog()
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dlg.setModal(False)  # 用户要求独立窗口

    if folder_paths:
        valid_dirs = [os.path.normpath(p) for p in folder_paths if os.path.isdir(p)]
        if valid_dirs:
            dlg._add_folder_paths(valid_dirs)

    dlg.show()
    _open_compare_dialogs.append(dlg)
    dlg.destroyed.connect(lambda: _cleanup_ref(dlg, _open_compare_dialogs))
    return dlg


def _cleanup_ref(obj, ref_list):
    """窗口销毁时清理引用列表中的自己。"""
    try:
        ref_list.remove(obj)
    except ValueError:
        pass
