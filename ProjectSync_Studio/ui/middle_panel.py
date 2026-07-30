# -*- coding: utf-8 -*-
"""
ProjectSync Studio - 中间栏：本地项目内容
  * 展示当前选中项目的本地文件结构（虚拟滚动 + 懒加载 + 缩略图）
  * 列表 / 缩略图视图切换，多种排序
  * 双击文件夹 → 软件内进入子目录（带「上级」返回）；双击文件 → 默认程序打开
  * 双向拖拽：接收来自 NAS 栏的拖入（复制进本地）；也可把本地文件拖到 NAS 栏
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config_manager import config_manager
from ..constants import VIEW_GRID, VIEW_LIST
from ..utils import check_overwrite_conflicts, open_file, open_in_explorer
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


class MiddlePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_path = ""      # 当前项目根目录
        self._current_dir = ""       # 当前浏览目录（可能为子目录）
        self._no_local = False       # 当前项目是否「无本地目录」
        self._browse_stack: list[str] = []
        self._worker = None
        self._copy_worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 顶部工具条
        top = QHBoxLayout()
        self.title = QLabel("本地项目内容")
        self.title.setStyleSheet("font-weight:500;font-size:13px;color:#1F2937;")
        self.back_btn = QPushButton("上级")
        self.back_btn.setToolTip("返回上级目录")
        self.back_btn.clicked.connect(self._back)
        self.open_btn = QPushButton("打开目录")
        self.open_btn.clicked.connect(self._open_dir)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setToolTip("重新读取本地目录（实时）")
        self.refresh_btn.clicked.connect(self.refresh_current)
        top.addWidget(self.title, 0)
        top.addStretch(1)
        top.addWidget(self.back_btn)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.open_btn)
        layout.addLayout(top)

        # 新建项目文件夹按钮（仅在无本地目录时显示）
        self.create_project_btn = QPushButton("📂 新建项目文件夹")
        self.create_project_btn.setObjectName("primary")
        self.create_project_btn.setToolTip("在本地项目根目录下创建该项目的文件夹")
        self.create_project_btn.clicked.connect(self._create_project_folder)
        self.create_project_btn.setVisible(False)
        layout.addWidget(self.create_project_btn)

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

        # 文件列表（可拖出 + 可接收）
        self.view = FileListView(
            draggable=True, droppable=True, on_open=self._on_item_open
        )
        self.view.files_dropped = self._on_files_dropped
        self.view.get_current_dir = lambda: self._current_dir or self._project_path
        layout.addWidget(self.view, 1)

        # 底部状态
        bottom = QHBoxLayout()
        self.spinner = SpinnerLabel()
        self.status = QLabel("")
        self.status.setStyleSheet("color:#6B7280; font-size:11px;")
        self._sel_count = QLabel("")
        self._sel_count.setStyleSheet("color:#2563EB; font-size:11px; font-weight:500;")
        bottom.addWidget(self.spinner)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self._sel_count)
        layout.addLayout(bottom)

        # 选中计数
        self.view.selection_count_changed.connect(self._on_sel_count)
        self._ascending = True

    # ---- 工具条交互 ----
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

    # ---- 加载本地项目 ----
    def load(self, local_path: str, no_local: bool = False):
        self._project_path = local_path or ""
        self._no_local = no_local
        self._current_dir = self._project_path
        self._browse_stack.clear()
        self.path_label.setText(self._current_dir)
        self.view.clear()
        self.status.setText("")
        if not self._current_dir or not os.path.isdir(self._current_dir):
            self.status.setText("（无本地项目文件夹）" if no_local else "（无效或不存在的目录）")
            self.create_project_btn.setVisible(bool(no_local))
            return
        self.create_project_btn.setVisible(False)
        self._start_list(self._current_dir)

    def refresh_current(self):
        """刷新按钮 / 右键「刷新」：重新读取当前目录（实时）。
        当前在子目录则重读该子目录；未绑定本地目录则按 _no_local 重判状态。"""
        if self._current_dir:
            self._start_list(self._current_dir)
        else:
            self.load(self._project_path, no_local=self._no_local)

    def _start_list(self, path: str):
        if not path:
            self.spinner.stop()
            return
        self.spinner.start("读取本地文件")
        if self._worker:
            if self._worker.isRunning():
                self._worker.requestInterruption()
                self._worker.wait(2000)
            # 断开旧信号防止累积泄漏
            try:
                self._worker.loaded.disconnect()
                self._worker.error.disconnect()
            except RuntimeError:
                pass
            self._worker = None
        self._worker = ListWorker(path, config_manager.ignore_patterns)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_loaded(self, path: str, entries: list):
        # 丢弃陈旧结果：用户可能在加载过程中切到了别的目录
        if path != self._current_dir:
            return
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
        self.status.setText(f"读取失败：{msg}")

    def _open_dir(self):
        if self._current_dir:
            open_in_explorer(self._current_dir)

    # ---- 软件内文件夹导航 ----
    def _on_item_open(self, path: str):
        if os.path.isdir(path):
            self._browse_stack.append(self._current_dir)
            self._current_dir = path
            self.path_label.setText(path)
            self._start_list(path)
        else:
            # 文件：用系统默认程序直接打开
            if not open_file(path):
                self.status.setText(f"无法打开：{path}")

    def _back(self):
        if self._browse_stack:
            self._current_dir = self._browse_stack.pop()
            self.path_label.setText(self._current_dir)
            self._start_list(self._current_dir)

    def _create_project_folder(self):
        """在本地根目录下创建项目文件夹，并更新项目绑定。"""
        win = self.window()
        proj = getattr(win, '_current_project', None) if win else None
        if not proj:
            return
        proj_name = proj.get("name") or ""
        local_roots = config_manager.local_roots
        if not local_roots:
            QMessageBox.warning(self, "无本地根", "请先在「设置」中配置本地项目根目录。")
            return
        root = local_roots[0]  # 使用第一个本地根
        default = proj_name or os.path.basename(proj.get("local_name", "").rstrip("/\\"))
        name, ok = QInputDialog.getText(self, "新建项目文件夹", "文件夹名称:", text=default)
        if not ok or not name.strip():
            return
        folder = os.path.join(root, name.strip())
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "创建失败", f"无法创建文件夹：\n{e}")
            return
        # 更新项目本地路径
        proj["local_path"] = folder
        config_manager.upsert_project(proj)
        if win and hasattr(win, '_current_project'):
            win._current_project = proj
        self.load(folder)
        self.status.setText(f"已创建：{folder}")

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
        dst = target_dir or self._current_dir or self._project_path
        if not dst:
            self.status.setText("请先选择一个本地项目再拖入文件")
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
        self.spinner.start("移动中" if move else "复制中")
        worker = MoveWorker(src_paths, dst) if move else CopyWorker(src_paths, dst)
        self._copy_worker = worker
        worker.progress.connect(
            lambda d, t, n: self.status.setText(("移动" if move else "复制") + f" {d}/{t}：{n}")
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
            f"{'移动' if move else '复制'}完成：成功 {ok}，失败 {fail}"
        )
        # 移动会改变源目录；复制到「当前目录」也会改变当前目录。二者都需刷新当前显示目录。
        # 复制到非当前目录时目标不在视图中，无需刷新。
        if move or self._drop_dst == self._current_dir:
            if self._current_dir:
                self._start_list(self._current_dir)
        # 兜底：清除可能为这些文件保留的「已剪切」灰色标记
        self.view.clear_cut_markers()
