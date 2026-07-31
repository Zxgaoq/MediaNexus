# -*- coding: utf-8 -*-
"""
MediaNexus - 文件列表视图（中栏 / 右栏共用）v2 重写版

v1 用 QListView + 自定义表头子控件 + 手动几何同步, 6 轮补丁仍死循环。
v2 改用 QTreeView 原生多列: 列头/列宽/滚动/末列填充全交 Qt, 零手动几何管理,
物理上不可能死循环。

特性:
  * QTreeView 原生 3 列 (名称/大小/修改时间), 列头竖线只在 Header, 数据行无竖线
  * QListView IconMode 缩略图网格视图, 可切换
  * QAbstractTableModel + fetchMore 懒加载, 万级文件虚拟滚动不卡
  * 双向拖拽、右键菜单、排序、缩略图后台加载
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Callable

from PySide6.QtCore import (
    QAbstractTableModel,
    QFileInfo,
    QItemSelectionModel,
    QModelIndex,
    QMimeData,
    QSize,
    Qt,
    QThread,
    Signal,
    QUrl,
)
from PySide6.QtGui import QColor, QCursor, QDrag, QFont, QIcon, QImage, QKeySequence, QPixmap
from collections import OrderedDict

# Thumbnail LRU cache: (path, grid_size) → QImage, max 500 entries
_thumb_cache: OrderedDict = OrderedDict()
_THUMB_CACHE_MAX = 500
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileIconProvider,
    QHeaderView,
    QListView,
    QMenu,
    QSizePolicy,
    QToolTip,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    GRID_CELL_H,
    GRID_CELL_W,
    ICON_SIZE_GRID,
    ICON_SIZE_LIST,
    IMAGE_EXTS,
    PAGE_SIZE,
    THUMBNAIL_MAX_COUNT,
    VIEW_GRID,
    VIEW_LIST,
    WORKER_WAIT_TIMEOUT_MS,
)
from ..clipboard import file_clipboard
from ..utils import copy_path_to_clipboard, human_readable_size, open_in_explorer

# 自然排序正则
_RE_NATURAL = re.compile(r"(\d+)")


def _natural_key(s: str) -> tuple:
    parts = _RE_NATURAL.split(s.lower())
    key = []
    for p in parts:
        if p.isdigit():
            key.append((1, int(p)))
        else:
            key.append((0, p))
    return tuple(key)


# 全局单例: 文件类型图标提供器 + 按扩展名/类型缓存
_ICON_PROVIDER = QFileIconProvider()
_ICON_CACHE: dict[str, QIcon] = {}


def _type_icon(name: str, is_dir: bool) -> QIcon:
    if is_dir:
        key = "<dir>"
        if key not in _ICON_CACHE:
            _ICON_CACHE[key] = _ICON_PROVIDER.icon(QFileIconProvider.Folder)
        return _ICON_CACHE[key]
    ext = os.path.splitext(name)[1].lower() or "<noext>"
    if ext not in _ICON_CACHE:
        icon = _ICON_PROVIDER.icon(QFileInfo(name))
        if icon.isNull():
            icon = _ICON_PROVIDER.icon(QFileIconProvider.File)
        _ICON_CACHE[ext] = icon
    return _ICON_CACHE[ext]


# ===================================================================
# 缩略图后台加载线程 (保持不变)
# ===================================================================
class ThumbnailLoader(QThread):
    ready = Signal(str, QImage)

    def __init__(self, paths: list[str], size: int):
        super().__init__()
        self._paths = paths
        self._size = size

    def run(self):
        for path in self._paths:
            if self.isInterruptionRequested():
                return
            try:
                img = QImage(path)
                if img.isNull():
                    continue
                if self.isInterruptionRequested():
                    return
                img = img.scaled(
                    self._size, self._size,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                if self.isInterruptionRequested():
                    return
                self.ready.emit(path, img)
            except Exception:
                continue


# ===================================================================
# 3 列表格模型 (QAbstractTableModel) + fetchMore 懒加载
# ===================================================================
class FileListViewModel(QAbstractTableModel):
    COL_NAME = 0
    COL_SIZE = 1
    COL_TIME = 2
    _HEADERS = ["名称", "大小", "修改时间"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all: list[dict] = []
        self._shown = 0
        self._thumbs: dict[str, QIcon] = {}
        self._row_of: dict[str, int] = {}
        self._search_text: str = ""
        self._filtered: list[int] = []
        self._cut_paths: set[str] = set()  # 当前被「剪切」待移动的文件路径集合

    def set_entries(self, entries: list[dict]) -> None:
        self.beginResetModel()
        self._all = entries or []
        self._shown = min(PAGE_SIZE, len(self._all))
        self._thumbs.clear()
        self._row_of = {e["path"]: i for i, e in enumerate(self._all)}
        self._search_text = ""
        self._filtered = []
        self.endResetModel()

    def apply_search(self, text: str) -> int:
        self._search_text = text.strip().lower()
        if not self._search_text:
            self._filtered = []
            self._shown = min(PAGE_SIZE, len(self._all))
        else:
            self._filtered = [
                i for i, e in enumerate(self._all)
                if self._search_text in e["name"].lower()
            ]
            self._shown = len(self._filtered)
        self.beginResetModel()
        self.endResetModel()
        return len(self._filtered) if self._search_text else len(self._all)

    def clear(self) -> None:
        self.set_entries([])

    # ---- 已「剪切」标记（视觉提示，区别于删除）----
    def mark_cut(self, paths: list[str]) -> None:
        self._cut_paths = set(paths or [])
        self._emit_cut_changed()

    def clear_cut(self) -> None:
        if self._cut_paths:
            self._cut_paths.clear()
            self._emit_cut_changed()

    def _emit_cut_changed(self) -> None:
        if self._shown > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._shown - 1, self.columnCount() - 1),
                [Qt.ForegroundRole, Qt.FontRole],
            )

    def entry_at(self, row: int) -> dict | None:
        return self._resolve(row)

    def all_entries(self) -> list[dict]:
        return self._all

    def set_thumbnail(self, path: str, icon: QIcon) -> None:
        self._thumbs[path] = icon
        row = self._row_of.get(path)
        if row is not None and row < self._shown:
            idx = self.index(row, self.COL_NAME)
            self.dataChanged.emit(idx, idx, [Qt.DecorationRole])

    # ---- 模型接口 ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._filtered) if self._search_text else self._shown

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 3

    def _resolve(self, row: int) -> dict | None:
        if self._search_text:
            return self._all[self._filtered[row]] if row < len(self._filtered) else None
        return self._all[row] if row < self._shown else None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        e = self._resolve(index.row())
        if e is None:
            return None
        col = index.column()
        if role == Qt.DisplayRole:
            if col == self.COL_NAME:
                return e["name"]
            if col == self.COL_SIZE:
                return "" if e["is_dir"] else human_readable_size(e["size"])
            if col == self.COL_TIME:
                mt = e.get("mtime")
                return datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M") if mt else ""
            return None
        # 已「剪切」待移动的项：灰色 + 删除线，明确区别于删除/普通项
        if role == Qt.ForegroundRole and e["path"] in self._cut_paths:
            return QColor(156, 163, 175)  # #9CA3AF 灰
        if role == Qt.FontRole and e["path"] in self._cut_paths:
            f = QFont()
            f.setStrikeOut(True)
            return f
        if role == Qt.DecorationRole and col == self.COL_NAME:
            thumb = self._thumbs.get(e["path"])
            if thumb is not None:
                return thumb
            return _type_icon(e["name"], e["is_dir"])
        if role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter | (Qt.AlignLeft if col == self.COL_NAME else Qt.AlignRight)
        if role == Qt.ToolTipRole:
            parts = [e["path"]]
            if not e["is_dir"]:
                parts.append(f"大小：{human_readable_size(e['size'])}")
            mt = e.get("mtime")
            if mt:
                parts.append("修改：" + datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M"))
            return "\n".join(parts)
        if role == Qt.UserRole:
            return e["path"]
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and 0 <= section < 3:
            if role == Qt.DisplayRole:
                return self._HEADERS[section]
            # 表头文字对齐与数据一致: 名称左对齐, 大小/修改时间右对齐
            if role == Qt.TextAlignmentRole:
                return Qt.AlignVCenter | (Qt.AlignLeft if section == 0 else Qt.AlignRight)
        return None

    # ---- 懒加载 (虚拟滚动核心) ----
    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        return not parent.isValid() and self._shown < len(self._all)

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid():
            return
        remainder = len(self._all) - self._shown
        n = min(PAGE_SIZE, remainder)
        if n <= 0:
            return
        self.beginInsertRows(QModelIndex(), self._shown, self._shown + n - 1)
        self._shown += n
        self.endInsertRows()

    def flags(self, index: QModelIndex):
        f = super().flags(index)
        if index.isValid():
            f |= Qt.ItemIsDragEnabled
            e = self._resolve(index.row())
            if e and e.get("is_dir"):
                f |= Qt.ItemIsDropEnabled
        else:
            f |= Qt.ItemIsDropEnabled
        return f

    def mimeData(self, indexes) -> QMimeData:  # noqa: N802
        data = QMimeData()
        urls = []
        seen = set()
        for idx in indexes:
            if idx.column() != self.COL_NAME:
                continue  # 每行只取第一列, 避免重复
            e = self.entry_at(idx.row())
            if e and e["path"] not in seen:
                seen.add(e["path"])
                urls.append(QUrl.fromLocalFile(e["path"]))
        data.setUrls(urls)
        return data


# ===================================================================
# 拖拽混入 (QTreeView / QListView 共用, _DragDropMixin 在前确保覆盖)
# ===================================================================
class _DragDropMixin:
    """双向拖拽逻辑, tree 和 grid 共用。需设置 self._dd_container = FileListView。"""

    def _dd(self):
        return self._dd_container

    def startDrag(self, supported_actions):  # noqa: N802
        indexes = self.selectedIndexes()
        if not indexes:
            return
        seen_rows = set()
        unique = []
        for idx in indexes:
            if idx.row() not in seen_rows:
                seen_rows.add(idx.row())
                unique.append(idx)
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData(unique))
        first = self.model().entry_at(unique[0].row()) if unique else None
        if first:
            ic = self.model().data(unique[0], Qt.DecorationRole)
            if isinstance(ic, QIcon):
                drag.setPixmap(ic.pixmap(32, 32))
        drag.exec(Qt.CopyAction | Qt.MoveAction)

    def supportedDropActions(self):  # noqa: N802
        return Qt.CopyAction | Qt.MoveAction

    def dragEnterEvent(self, event):  # noqa: N802
        if self._dd()._droppable and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802
        if not (self._dd()._droppable and event.mimeData().hasUrls()):
            event.ignore()
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        idx = self.indexAt(pos)
        if idx.isValid():
            e = self.model().entry_at(idx.row())
            if e and e.get("is_dir"):
                event.setDropAction(
                    Qt.MoveAction if event.source() is self else self._effective_action(event))
            else:
                event.setDropAction(self._effective_action(event))
        else:
            event.setDropAction(self._effective_action(event))
        event.acceptProposedAction()

    def _effective_action(self, event) -> Qt.DropAction:
        mods = event.modifiers()
        if mods & Qt.ControlModifier:
            return Qt.CopyAction
        if mods & Qt.ShiftModifier:
            return Qt.MoveAction
        return Qt.MoveAction if event.source() is self else Qt.CopyAction

    def dropEvent(self, event):  # noqa: N802
        if not (self._dd()._droppable and event.mimeData().hasUrls()):
            event.ignore()
            return
        src_paths = []
        for u in event.mimeData().urls():
            p = u.toLocalFile()
            if not p:
                p = u.path()
            if p and not os.path.exists(p) and p.startswith("/"):
                p2 = p.replace("/", "\\")
                if os.path.exists(p2):
                    p = p2
            if p:
                src_paths.append(p)
        if not src_paths:
            event.ignore()
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        idx = self.indexAt(pos)
        target_dir = None
        if idx.isValid():
            e = self.model().entry_at(idx.row())
            if e and e.get("is_dir"):
                target_dir = e["path"]
        action = self._effective_action(event)
        move = action == Qt.MoveAction
        if event.source() is self and target_dir is None:
            event.ignore()
            return
        if self._dd().files_dropped is not None:
            self._dd().files_dropped(src_paths, target_dir, move)
        event.setDropAction(action)
        event.acceptProposedAction()


# ===================================================================
# 列表视图 (QTreeView) — 原生多列, 列头/列宽/滚动全交 Qt
# ===================================================================
_TREE_QSS = """
QTreeView { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:8px; outline:none; }
QTreeView::item { padding:3px 4px; border:none; border-bottom:1px solid #F3F4F6; }
QTreeView::item:hover { background-color:#F3F4F6; }
QTreeView::item:selected { background-color:#DBEAFE; color:#1D4ED8; }
QHeaderView::section { background-color:#F9FAFB; border:none;
    border-right:1px solid #E5E7EB; border-bottom:1px solid #E5E7EB;
    padding:4px 8px; color:#374151; }
"""


class _FileTree(_DragDropMixin, QTreeView):
    def __init__(self, container: "FileListView"):
        super().__init__(container)
        self._dd_container = container
        self.setRootIsDecorated(False)
        self.setItemsExpandable(False)
        self.setIndentation(0)  # 消除树形缩进, 确保数据行与列头左对齐
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setIconSize(QSize(ICON_SIZE_LIST, ICON_SIZE_LIST))
        self.setDragDropOverwriteMode(False)
        # 列头: 全 Interactive + StretchLastSection (Qt 原生填视口, 无冲突)
        h = self.header()
        h.setSectionsMovable(False)
        h.setStretchLastSection(True)
        h.setSectionResizeMode(0, QHeaderView.Interactive)
        h.setSectionResizeMode(1, QHeaderView.Interactive)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        h.setMinimumSectionSize(40)
        # 列宽初始值在 setModel 之后设置 (见 FileListView.__init__)
        self.setStyleSheet(_TREE_QSS)

    def contextMenuEvent(self, event):  # noqa: N802
        self._dd_container._on_context_menu(event)

    def keyPressEvent(self, event):  # noqa: N802
        c = self._dd_container
        if event.matches(QKeySequence.Copy):
            c._on_copy()
        elif event.matches(QKeySequence.Cut):
            c._on_cut()
        elif event.matches(QKeySequence.Paste):
            c._on_paste()
        elif event.matches(QKeySequence.SelectAll):
            c._on_select_all()
        elif event.key() == Qt.Key_Delete:
            c._on_delete()
        elif event.key() == Qt.Key_F2:
            c._on_rename_current()
        else:
            super().keyPressEvent(event)


# ===================================================================
# 网格视图 (QListView IconMode) — 缩略图
# ===================================================================
class _FileGrid(_DragDropMixin, QListView):
    def __init__(self, container: "FileListView"):
        super().__init__(container)
        self._dd_container = container
        self.setViewMode(QListView.IconMode)
        self.setIconSize(QSize(ICON_SIZE_GRID, ICON_SIZE_GRID))
        self.setGridSize(QSize(GRID_CELL_W, GRID_CELL_H))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setWordWrap(True)
        self.setSpacing(6)
        self.setMovement(QListView.Movement.Static)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setUniformItemSizes(True)
        self.setDragDropOverwriteMode(False)
        self.setModelColumn(0)

    def contextMenuEvent(self, event):  # noqa: N802
        self._dd_container._on_context_menu(event)

    def keyPressEvent(self, event):  # noqa: N802
        c = self._dd_container
        if event.matches(QKeySequence.Copy):
            c._on_copy()
        elif event.matches(QKeySequence.Cut):
            c._on_cut()
        elif event.matches(QKeySequence.Paste):
            c._on_paste()
        elif event.matches(QKeySequence.SelectAll):
            c._on_select_all()
        elif event.key() == Qt.Key_Delete:
            c._on_delete()
        elif event.key() == Qt.Key_F2:
            c._on_rename_current()
        else:
            super().keyPressEvent(event)


# ===================================================================
# FileListView — 容器, 在 _FileTree (列表) 和 _FileGrid (缩略图) 间切换
# ===================================================================
class FileListView(QWidget):
    """通用文件列表视图, 支持双向拖拽、缩略图、视图切换、排序。"""
    selection_count_changed = Signal(int)

    def __init__(
        self,
        draggable: bool = False,
        droppable: bool = False,
        on_open: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._draggable = draggable
        self._droppable = droppable
        self._on_open = on_open
        self.files_dropped = None
        self.send_to_peer = None
        self.get_current_dir = None
        self._view_mode = VIEW_LIST
        self._thumb_loader: ThumbnailLoader | None = None
        self._sort_key = "name"
        self._sort_reverse = False

        self._model = FileListViewModel(self)

        self._tree = _FileTree(self)
        self._tree.setModel(self._model)
        # 列宽初始值 (必须在 setModel 之后, 否则 QHeaderView 不知道列数)
        _h = self._tree.header()
        _h.resizeSection(0, 200)
        _h.resizeSection(1, 90)
        # 第 3 列 (修改时间) 由 StretchLastSection 自动填满剩余视口

        self._grid = _FileGrid(self)
        self._grid.setModel(self._model)
        self._grid.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tree)
        layout.addWidget(self._grid)

        # 水平 Ignored: 由 QSplitter stretch 因子决定栏宽; 垂直 Expanding 填满
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        self._tree.doubleClicked.connect(self._on_double_click)
        self._grid.doubleClicked.connect(self._on_double_click)
        self._tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._grid.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self._apply_drag_config()

    def _active_view(self):
        return self._tree if self._view_mode == VIEW_LIST else self._grid

    def _apply_drag_config(self) -> None:
        for v in (self._tree, self._grid):
            v.setDragEnabled(self._draggable)
            v.setAcceptDrops(self._droppable)
            if self._draggable and self._droppable:
                v.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            elif self._droppable:
                v.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
            elif self._draggable:
                v.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
            else:
                v.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
            if self._droppable:
                v.setDropIndicatorShown(True)

    # ---- 公共接口 (兼容 MiddlePanel / RightPanel) ----
    def set_entries(self, entries: list[dict]) -> None:
        # 保存当前选中路径
        saved_paths = set(self.selected_paths())

        entries = self._sorted(entries or [])
        self._model.set_entries(entries)

        # 恢复选中状态：根据保存的路径在新模型中定位行号
        if saved_paths and self._model._row_of:
            view = self._active_view()
            sel_model = view.selectionModel()
            flags = QItemSelectionModel.Select | QItemSelectionModel.Rows
            first_idx = None
            for path in saved_paths:
                row = self._model._row_of.get(path)
                if row is not None:
                    idx = self._model.index(row, 0)
                    sel_model.select(idx, flags)
                    if first_idx is None:
                        first_idx = idx
            # 滚动到第一个恢复的选中行，保持可视
            if first_idx is not None:
                view.scrollTo(first_idx, QAbstractItemView.ScrollHint.EnsureVisible)

        self._restart_thumbnails()

    def clear(self) -> None:
        self._stop_thumbnails()
        self._model.clear()

    def selected_paths(self) -> list[str]:
        view = self._active_view()
        out, seen = [], set()
        for idx in view.selectedIndexes():
            if idx.column() != 0:
                continue
            e = self._model.entry_at(idx.row())
            if e and e["path"] not in seen:
                seen.add(e["path"])
                out.append(e["path"])
        return out

    def model(self) -> FileListViewModel:
        return self._model

    # ---- 已「剪切」视觉标记（供面板在 finished 回调里兜底清除）----
    def set_cut_markers(self, paths: list[str]) -> None:
        self._model.mark_cut(paths)

    def clear_cut_markers(self) -> None:
        self._model.clear_cut()

    def selectionModel(self):  # noqa: N802
        return self._active_view().selectionModel()

    # ---- 视图模式 ----
    def set_view_mode(self, mode: str) -> None:
        if mode == self._view_mode:
            return
        self._view_mode = mode
        if mode == VIEW_GRID:
            self._tree.hide()
            self._grid.show()
        else:
            self._grid.hide()
            self._tree.show()
        self._restart_thumbnails()

    def view_mode(self) -> str:
        return self._view_mode

    # ---- 排序 ----
    def set_sort(self, key: str, reverse: bool = False) -> None:
        self._sort_key = key
        self._sort_reverse = reverse
        entries = self._model.all_entries()
        if entries:
            self.set_entries(entries)

    def _sorted(self, entries: list[dict]) -> list[dict]:
        key = self._sort_key
        rev = self._sort_reverse
        if key == "size":
            keyfn = lambda e: (not e["is_dir"], e.get("size", 0))
        elif key == "mtime":
            keyfn = lambda e: (not e["is_dir"], e.get("mtime", 0))
        elif key == "type":
            keyfn = lambda e: (
                not e["is_dir"],
                os.path.splitext(e["name"])[1].lower(),
                e["name"].lower(),
            )
        else:
            keyfn = lambda e: (not e["is_dir"], _natural_key(e["name"]))
        dirs = [e for e in entries if e["is_dir"]]
        files = [e for e in entries if not e["is_dir"]]
        dkey = (lambda e: keyfn(e)[1:])
        dirs.sort(key=dkey, reverse=rev)
        files.sort(key=dkey, reverse=rev)
        return dirs + files

    # ---- 缩略图 ----
    def _stop_thumbnails(self) -> None:
        loader = self._thumb_loader
        if loader is not None:
            loader.requestInterruption()
            if loader.isRunning():
                loader.wait(WORKER_WAIT_TIMEOUT_MS)
        self._thumb_loader = None

    def _restart_thumbnails(self) -> None:
        self._stop_thumbnails()
        if self._view_mode != VIEW_GRID:
            return
        paths = [
            e["path"] for e in self._model.all_entries()
            if not e["is_dir"] and os.path.splitext(e["name"])[1].lower() in IMAGE_EXTS
        ][:THUMBNAIL_MAX_COUNT]
        if not paths:
            return
        # LRU cache: 先查缓存，命中则直接 emit — 节省 QImage 加载
        uncached: list[str] = []
        cache_key_size = ICON_SIZE_GRID
        for p in paths:
            key = (p, cache_key_size)
            if key in _thumb_cache:
                _thumb_cache.move_to_end(key)
                self._on_thumb_ready(p, _thumb_cache[key])
            else:
                uncached.append(p)
        if uncached:
            self._thumb_loader = ThumbnailLoader(uncached, ICON_SIZE_GRID)
            self._thumb_loader.ready.connect(self._on_thumb_ready)
            self._thumb_loader.start()

    def _on_thumb_ready(self, path: str, image: QImage) -> None:
        # LRU: 存入缓存（淘汰最老条目）
        key = (path, ICON_SIZE_GRID)
        _thumb_cache[key] = image
        _thumb_cache.move_to_end(key)
        while len(_thumb_cache) > _THUMB_CACHE_MAX:
            _thumb_cache.popitem(last=False)
        pix = QPixmap.fromImage(image)
        if not pix.isNull():
            self._model.set_thumbnail(path, QIcon(pix))

    # ---- 交互 ----
    def _on_double_click(self, index: QModelIndex) -> None:
        e = self._model.entry_at(index.row())
        if not e:
            return
        if self._on_open:
            self._on_open(e["path"])
        else:
            open_in_explorer(e["path"])

    def _on_selection_changed(self) -> None:
        view = self._active_view()
        count = len({idx.row() for idx in view.selectedIndexes()})
        self.selection_count_changed.emit(count)

    # ---- 复制 / 剪切 / 粘贴 ----
    def _on_copy(self, paths: list[str] | None = None) -> None:
        paths = paths or self.selected_paths()
        if not paths:
            return
        file_clipboard.set(paths, "copy")
        self._model.clear_cut()  # 复制不是剪切，清除可能的灰色标记
        QToolTip.showText(QCursor.pos(), f"已复制 {len(paths)} 项")

    def _on_cut(self, paths: list[str] | None = None) -> None:
        paths = paths or self.selected_paths()
        if not paths:
            return
        file_clipboard.set(paths, "cut")
        self._model.mark_cut(paths)  # 视觉标记：灰色 + 删除线，提示「待移动」
        QToolTip.showText(QCursor.pos(), f"已剪切 {len(paths)} 项")

    def _on_paste(self, index=None) -> None:
        paths = (
            file_clipboard.get()
            if file_clipboard.has_content
            else file_clipboard.read_system_files()
        )
        if not paths:
            QToolTip.showText(QCursor.pos(), "剪贴板没有可粘贴的文件")
            return
        target = self._paste_target_for(index)
        if not target:
            return
        move = file_clipboard.has_content and file_clipboard.is_cut()
        if move:
            file_clipboard.clear()
        self._model.clear_cut()  # 粘贴后清除灰色标记（剪切已消费；复制也不应残留）
        if self.files_dropped is not None:
            self.files_dropped(paths, target, move)

    def _paste_target_for(self, index=None) -> str:
        if index is not None and index.isValid():
            e = self._model.entry_at(index.row())
            if e and e.get("is_dir"):
                return e["path"]
        if self.get_current_dir:
            return self.get_current_dir() or ""
        return ""

    def _on_select_all(self) -> None:
        self._active_view().selectAll()

    def _on_rename_current(self) -> None:
        paths = self.selected_paths()
        if len(paths) == 1:
            self._rename_entry(paths[0])

    # ---- 右键菜单 ----
    def _on_context_menu(self, event) -> None:
        from PySide6.QtWidgets import QMessageBox

        view = self._active_view()
        index = view.indexAt(event.pos())
        clicked = self._model.entry_at(index.row()) if index.isValid() else None
        sel = self.selected_paths()
        # 右键未选中项时，以被点击项作为有效选择，保证菜单可用
        effective = sel if sel else ([clicked["path"]] if clicked else [])
        has_sel = bool(effective)

        menu = QMenu(self)

        open_act = copy_path_act = copy_act = cut_act = paste_act = None
        rename_act = delete_act = None

        if clicked:
            open_act = menu.addAction("在资源管理器中打开")
            copy_path_act = menu.addAction("复制路径")
            menu.addSeparator()
            copy_act = menu.addAction("复制\tCtrl+C")
            cut_act = menu.addAction("剪切\tCtrl+X")
            paste_act = menu.addAction("粘贴\tCtrl+V")
            menu.addSeparator()
            rename_act = menu.addAction("重命名\tF2")
            delete_act = menu.addAction("删除\tDel")
        else:
            paste_act = menu.addAction("粘贴\tCtrl+V")

        # 可用状态
        can_paste = file_clipboard.has_content or bool(file_clipboard.read_system_files())
        if paste_act is not None:
            paste_act.setEnabled(can_paste)
        if copy_act is not None:
            copy_act.setEnabled(has_sel)
        if cut_act is not None:
            cut_act.setEnabled(has_sel)
        if rename_act is not None:
            rename_act.setEnabled(len(effective) == 1)
        if delete_act is not None:
            delete_act.setEnabled(has_sel)

        new_folder_act = new_file_act = None
        if self.get_current_dir and self.get_current_dir():
            menu.addSeparator()
            new_folder_act = menu.addAction("新建文件夹")
            new_file_act = menu.addAction("新建文件")

        send_act = None
        if effective and self.send_to_peer is not None:
            menu.addSeparator()
            send_act = menu.addAction("发送到对侧")

        # ── QC 检测 ──
        VIDEO_EXTS = {
            ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
            ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
            ".m2ts", ".mts", ".vob", ".ogv", ".rmvb", ".divx",
        }
        qc_files: list[str] = []
        qc_folders: list[str] = []
        if effective:
            for p in effective:
                ext = os.path.splitext(p)[1].lower()
                if ext in VIDEO_EXTS:
                    qc_files.append(p)
                elif os.path.isdir(p):
                    qc_folders.append(p)
                else:
                    qc_files.append(p)  # 未知类型按文件对待

        qc_detect_act = None
        qc_compare_act = None
        if qc_files or qc_folders:
            menu.addSeparator()
            qc_detect_act = menu.addAction("🔍 QC检测")
        if len(qc_folders) >= 2:
            qc_compare_act = menu.addAction("📐 多版本对比")

        menu.addSeparator()
        refresh_act = menu.addAction("刷新")
        action = menu.exec(event.globalPos())

        if action == open_act and clicked:
            open_in_explorer(clicked["path"])
        elif action == copy_path_act and clicked:
            ok = copy_path_to_clipboard(clicked["path"])
            if self.window():
                QMessageBox.information(
                    self, "复制路径",
                    "已复制：\n" + clicked["path"] if ok else "复制失败")
        elif action == copy_act and has_sel:
            self._on_copy(effective)
        elif action == cut_act and has_sel:
            self._on_cut(effective)
        elif action == paste_act:
            self._on_paste(index if clicked else None)
        elif action == rename_act and len(effective) == 1:
            self._rename_entry(effective[0])
        elif action == delete_act and has_sel:
            self._delete_entries(effective)
        elif action == new_folder_act:
            self._new_folder()
        elif action == new_file_act:
            self._new_file()
        elif action == send_act and effective:
            self.send_to_peer(effective)
        elif action == refresh_act:
            if self.window() and hasattr(self.window(), "refresh_current"):
                self.window().refresh_current()
        elif action == qc_detect_act and qc_detect_act is not None:
            self._on_qc_detect(qc_files, qc_folders)
        elif action == qc_compare_act and qc_compare_act is not None:
            self._on_qc_compare(qc_folders)

    # ── QC 检测 / 多版本对比 ──
    @staticmethod
    def _on_qc_detect(files: list[str], folders: list[str]):
        """右键「QC检测」：打开 QC 窗口，预载选中视频文件，目录仅扫描一级子目录。"""
        from ..qc_bridge import open_qc_detection
        all_paths = list(files)
        if folders:
            for folder in folders:
                try:
                    for entry in os.scandir(folder):
                        ext = os.path.splitext(entry.name)[1].lower()
                        video_exts = {
                            ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
                            ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
                            ".m2ts", ".mts", ".vob", ".ogv", ".rmvb", ".divx",
                        }
                        if entry.is_file() and ext in video_exts:
                            all_paths.append(entry.path)
                except PermissionError:
                    continue
        open_qc_detection(all_paths)

    @staticmethod
    def _on_qc_compare(folders: list[str]):
        """右键「多版本对比」：打开对比窗口，预载选中文件夹。"""
        from ..qc_bridge import open_multi_version_compare
        open_multi_version_compare(folders)

    def _on_delete(self, paths: list[str] | None = None) -> None:
        paths = paths or self.selected_paths()
        if paths:
            self._delete_entries(paths)

    def _delete_entries(self, paths: list[str]):
        from PySide6.QtWidgets import QMessageBox
        import shutil

        if not paths:
            return
        names = [os.path.basename(p.rstrip("/\\")) for p in paths]
        if len(names) == 1:
            is_dir = os.path.isdir(paths[0])
            msg = f"确定删除{'文件夹' if is_dir else '文件'}「{names[0]}」吗？\n\n此操作不可恢复！"
        else:
            preview = "\n".join(f"  {n}" for n in names[:10])
            if len(names) > 10:
                preview += f"\n  ... 等共 {len(names)} 项"
            msg = f"确定删除以下 {len(names)} 个项目吗？\n\n{preview}\n\n此操作不可恢复！"
        reply = QMessageBox.question(
            self, "确认删除", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        failed = []
        for p in paths:
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
            except OSError as e:
                failed.append(f"{os.path.basename(p)}: {e}")
        if failed:
            QMessageBox.warning(self, "删除失败", "\n".join(failed))
        if self.window() and hasattr(self.window(), "refresh_current"):
            self.window().refresh_current()

    def _rename_entry(self, path: str):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        old_name = os.path.basename(path.rstrip("/\\"))
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=old_name)
        if not ok or not new_name or new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(path), new_name)
        try:
            os.rename(path, new_path)
        except OSError as e:
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        if self.window() and hasattr(self.window(), "refresh_current"):
            self.window().refresh_current()

    def _new_folder(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        if not self.get_current_dir:
            return
        base = self.get_current_dir()
        if not base:
            return
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称：", text="新建文件夹")
        if not ok or not name:
            return
        new_path = os.path.join(base, name)
        try:
            os.makedirs(new_path, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "创建失败", str(e))
            return
        if self.window() and hasattr(self.window(), "refresh_current"):
            self.window().refresh_current()

    def _new_file(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        if not self.get_current_dir:
            return
        base = self.get_current_dir()
        if not base:
            return
        name, ok = QInputDialog.getText(self, "新建文件", "文件名称：", text="新建文件.txt")
        if not ok or not name:
            return
        new_path = os.path.join(base, name)
        try:
            if os.path.exists(new_path):
                QMessageBox.warning(self, "创建失败", "该名称已存在")
                return
            with open(new_path, "w", encoding="utf-8"):
                pass
        except OSError as e:
            QMessageBox.warning(self, "创建失败", str(e))
            return
        if self.window() and hasattr(self.window(), "refresh_current"):
            self.window().refresh_current()

    def closeEvent(self, event):  # noqa: N802
        self._stop_thumbnails()
        super().closeEvent(event)
