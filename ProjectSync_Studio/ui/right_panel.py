# -*- coding: utf-8 -*-
"""
ProjectSync Studio - 右侧栏：服务器匹配内容
  * 顶部下拉切换器：列出所有候选服务器路径及相似度百分比，已确认项高亮
  * 「确认为此项目」→ 持久化绑定；「排除此结果」→ 降低权重并重新匹配
  * 文件列表（拖拽源）：展示当前候选内容，双击文件夹可深入导航
  * 服务器访问失败时自动重试，并支持手动重试
"""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config_manager import config_manager
from ..constants import NAS_RETRY_INTERVAL_MS, NAS_RETRY_TIMES, VIEW_GRID, VIEW_LIST
from ..utils import check_overwrite_conflicts, open_file
from ..workers import CopyWorker, ListWorker, MoveWorker
from .file_list_view import FileListView
from .widgets import SpinnerLabel

# 排序选项：(显示文本, key)
SORT_OPTIONS = [
    ("名称", "name"),
    ("大小", "size"),
    ("修改时间", "mtime"),
    ("类型", "type"),
]


class RightPanel(QWidget):
    # 确认/排除后通知主窗口刷新左栏与状态
    matched_changed = Signal()
    need_rematch = Signal(str)  # local_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._candidates: list[dict] = []
        self._current_root = ""
        self._browse_stack: list[str] = []
        self._worker = None
        self._copy_worker = None
        self._retry_count = 0
        self._ascending = True
        self._retry_timer = QTimer()
        self._retry_timer.timeout.connect(self._retry_now)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 标题
        self.title = QLabel("服务器内容")
        self.title.setStyleSheet("font-weight:500;font-size:13px;color:#1F2937;")
        layout.addWidget(self.title)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.back_btn = QPushButton("上级")
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setToolTip("从服务器实时重新读取当前目录（不走缓存索引）")
        self.refresh_btn.clicked.connect(self._refresh)
        self.back_btn.clicked.connect(self._back)
        btn_row.addWidget(self.back_btn)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # 搜索栏
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索当前目录文件名… (Ctrl+F)")
        self.search_box.textChanged.connect(self._apply_search)
        layout.addWidget(self.search_box)

        # 视图 / 排序 工具条
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color:#6B7280; font-size:11px;")
        self.path_label.setWordWrap(False)
        self.path_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        tools.addWidget(self.path_label, 1)
        tools.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        for text, _ in SORT_OPTIONS:
            self.sort_combo.addItem(text)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        tools.addWidget(self.sort_combo)
        self.order_btn = QPushButton("升序")
        self.order_btn.setFixedWidth(55)
        self.order_btn.setToolTip("点击切换升序 / 降序")
        self.order_btn.clicked.connect(self._toggle_order)
        tools.addWidget(self.order_btn)
        self.view_btn = QPushButton("缩略图")
        self.view_btn.setToolTip("在列表 / 缩略图视图间切换")
        self.view_btn.clicked.connect(self._toggle_view)
        tools.addWidget(self.view_btn)
        layout.addLayout(tools)

        # 文件列表（可拖出 + 可接收：本地文件拖入 = 复制到当前 NAS 目录）
        self.view = FileListView(
            draggable=True, droppable=True, on_open=self._on_item_open
        )
        self.view.files_dropped = self._on_files_dropped
        self.view.get_current_dir = lambda: self._current_root
        layout.addWidget(self.view, 1)

        # 底部
        bottom = QHBoxLayout()
        self.spinner = SpinnerLabel()
        self.status = QLabel("")
        self.status.setStyleSheet("color:#6B7280; font-size:11px;")
        self.retry_btn = QPushButton("重试")
        self.retry_btn.setVisible(False)
        self.retry_btn.clicked.connect(self._manual_retry)
        bottom.addWidget(self.spinner)
        bottom.addWidget(self.status, 1)
        self._sel_count = QLabel("")
        self._sel_count.setStyleSheet("color:#2563EB; font-size:11px; font-weight:500;")
        bottom.addWidget(self._sel_count)
        bottom.addWidget(self.retry_btn)
        layout.addLayout(bottom)

        # 选中计数
        self.view.selection_count_changed.connect(self._on_sel_count)

    # --------------------------- 工具条交互 ---------------------------
    def _on_sort_changed(self, index: int):
        key = SORT_OPTIONS[index][1]
        self.view.set_sort(key, reverse=not self._ascending)

    def _toggle_order(self):
        self._ascending = not self._ascending
        self.order_btn.setText("升序" if self._ascending else "降序")
        key = SORT_OPTIONS[self.sort_combo.currentIndex()][1]
        self.view.set_sort(key, reverse=not self._ascending)

    def _toggle_view(self):
        if self.view.view_mode() == VIEW_GRID:
            self.view.set_view_mode(VIEW_LIST)
            self.view_btn.setText("缩略图")
        else:
            self.view.set_view_mode(VIEW_GRID)
            self.view_btn.setText("列表")

        # ---- 接收拖入（Windows 风格：跨栏=复制，同栏拖到文件夹=移动） ----
    def _stop_copy_worker(self) -> None:
        worker = self._copy_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(2000)
            try:
                worker.progress.disconnect()
                worker.finished.disconnect()
            except RuntimeError:
                pass
        self._copy_worker = None

    def _on_files_dropped(self, src_paths: list[str], target_dir: str | None, move: bool):
        dst = target_dir or self._current_root
        if not dst:
            self.status.setText("请先选择一个 NAS 目录再拖入文件")
            return
        # 同名文件检查
        if not check_overwrite_conflicts(self, src_paths, dst):
            return
        # 有复制/移动任务正在进行中，提示等待完成，不打断
        if self._copy_worker is not None and self._copy_worker.isRunning():
            self.status.setText("等待上一次复制/移动完成…")
            return
        self._drop_move = move
        self._drop_dst = dst
        self._stop_copy_worker()
        self.spinner.start("移动中" if move else "上传到服务器")
        worker = MoveWorker(src_paths, dst) if move else CopyWorker(src_paths, dst)
        self._copy_worker = worker
        worker.progress.connect(
            lambda d, t, n: self.status.setText(("移动" if move else "上传") + f" {d}/{t}：{n}")
        )
        worker.finished.connect(
            lambda ok, fail: self._on_dropped_done(ok, fail)
        )
        worker.start()

    def _on_dropped_done(self, ok: int, fail: int) -> None:
        """复制/移动完成后的刷新：确保当前显示的（源）目录立即更新，
        避免剪切移动后源列表里的文件仍然残留、直到手动刷新。"""
        move = self._drop_move
        self.spinner.stop()
        self.status.setText(
            f"{'移动' if move else '上传'}完成：成功 {ok}，失败 {fail}"
        )
        # 移动会改变源目录；复制到「当前目录」也会改变当前目录。二者都需刷新当前显示目录。
        # 复制到非当前目录时目标不在视图中，无需刷新。
        if move or self._drop_dst == self._current_root:
            if self._current_root:
                self._load_contents(self._current_root)
        # 兜底：清除可能为这些文件保留的「已剪切」灰色标记
        self.view.clear_cut_markers()

    # --------------------------- 载入一个项目 ---------------------------
    def load(self, project: dict):
        self._project = project
        self._browse_stack.clear()
        confirmed = project.get("confirmed_nas_path", "")
        self._current_root = confirmed
        if not confirmed:
            self.view.clear()
            self.path_label.setText("（未确认服务器目录）")
            self.status.setText('右键侧栏项目 ->「重新匹配」选择服务器目录，或选择"无服务器的项目文件夹"')
            return
        self._load_contents(self._current_root)

    # --------------------------- 内容加载（带重试） ---------------------------
    def _load_contents(self, path: str):
        if not path:
            self.view.clear()
            self.path_label.setText("（无匹配候选）")
            self.status.setText("请先在左侧确认或排除，或调整匹配阈值后重新匹配")
            return
        self.path_label.setText(path)
        self.view.clear()
        self.status.setText("")
        self.retry_btn.setVisible(False)
        self._retry_count = 0
        self._start_worker(path)

    def _start_worker(self, path: str, force_live: bool = False):
        self.spinner.start("访问服务器")
        if self._worker:
            if self._worker.isRunning():
                self._worker.requestInterruption()
                self._worker.wait(2000)
            try:
                self._worker.loaded.disconnect()
                self._worker.error.disconnect()
            except RuntimeError:
                pass
            self._worker = None
        self._worker = ListWorker(path, config_manager.ignore_patterns, force_live=force_live)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_loaded(self, path: str, entries: list):
        if path != self._current_root:
            return  # 已切换到别的目录，丢弃旧结果
        self.spinner.stop()
        self.view.set_entries(entries)
        self.status.setText(f"共 {len(entries)} 项")

    def _apply_search(self, text: str):
        """搜索过滤当前文件列表。"""
        model = self.view.model()
        if hasattr(model, "apply_search"):
            count = model.apply_search(text)
            self.status.setText(f"找到 {count} 项" if text.strip() else f"共 {count} 项")

    def _on_sel_count(self, count: int):
        """更新选中文件计数。"""
        self._sel_count.setText(f"已选 {count} 项" if count else "")

    def _on_error(self, path: str, msg: str):
        self.spinner.stop()
        if self._retry_count < NAS_RETRY_TIMES:
            self._retry_count += 1
            self.status.setText(
                f"服务器访问失败，{NAS_RETRY_INTERVAL_MS/1000:.1f}s 后第 {self._retry_count} 次重试…"
            )
            self._retry_timer.start(NAS_RETRY_INTERVAL_MS)
        else:
            self.status.setText(f"无法访问服务器：{msg}")
            self.retry_btn.setVisible(True)

    def _retry_now(self):
        self._retry_timer.stop()
        self._start_worker(self._current_root)

    def _manual_retry(self):
        self.retry_btn.setVisible(False)
        self._retry_count = 0
        self._start_worker(self._current_root)

    # --------------------------- 文件夹导航 ---------------------------
    def _on_item_open(self, path: str):
        if os.path.isdir(path):
            self._browse_stack.append(self._current_root)
            self._current_root = path
            self._load_contents(path)
        else:
            # 文件：用系统默认程序直接打开（不再打开两次资源管理器）
            if not open_file(path):
                self.status.setText(f"无法打开：{path}")

    def _refresh(self):
        """刷新按钮：优先使用 watcher 实时索引做轻量刷新，无 watcher 时回退子树扫描。"""
        root = (self._project or {}).get("confirmed_nas_path") or self._current_root
        if not root:
            return
        win = self.window()
        # 检查 watcher 是否正在监控当前项目根
        watcher_active = (
            hasattr(win, "_watcher")
            and root.rstrip("/\\") in win._watcher.watching_roots()
        )
        if watcher_active:
            # watcher 活跃：索引已是最新，只需轻量刷新当前目录 + 直接从索引读
            from .. import indexer as nas_indexer
            target = self._current_root or root
            try:
                nas_indexer.indexer.refresh_dir(target)
                entries = nas_indexer.indexer.list_children(target)
                if entries:
                    self.path_label.setText(target)
                    self.view.set_entries(entries)
                    self.status.setText(f"共 {len(entries)} 项")
                    return
            except Exception:  # noqa: BLE001
                pass
            # fallback：索引读取失败时走正常 ListWorker 路径
            self._load_contents(target)
        else:
            # watcher 未活跃：回退到旧的子树扫描
            self.status.setText("正在增量刷新服务器（含子文件夹）…")
            if hasattr(win, "_refresh_server_project"):
                win._refresh_server_project(root, on_done=self._after_server_refresh)
            else:
                self._start_worker(root, force_live=True)

    def _after_server_refresh(self, root: str):
        """子树刷新完成后：用已更新的索引重新加载当前显示的目录。"""
        self.spinner.stop()
        self.status.setText("服务器已刷新（含子文件夹）")
        if self._current_root:
            self._load_contents(self._current_root)

    def refresh_current(self):
        """供右键菜单「刷新」调用：增量刷新当前项目服务器内容（含子文件夹）。"""
        self._refresh()

    def _back(self):
        if self._browse_stack:
            self._current_root = self._browse_stack.pop()
            self._load_contents(self._current_root)

    # --------------------------- 导航 ---------------------------
