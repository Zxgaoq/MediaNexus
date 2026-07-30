# -*- coding: utf-8 -*-
"""
ProjectSync Studio - 左侧边栏：项目导航
  * 列出所有已识别的本地项目，带状态标识 ✅ / ⚠️ / ❌ / ❓(缺失)
  * 顶部搜索过滤 + 状态筛选 + 添加项目按钮
  * 右键菜单：删除项目(确认) / 资源管理器打开 / 重新匹配
  * 排序：名称(自然排序：数字按数值)、修改时间(文件夹文件系统时间) + 升降序切换
  * 刷新时自动清理已删除的文件夹
  * 点击项目 → 触发 project_selected 信号，刷新右侧双栏
"""
from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt, Signal, QEvent, QRect, QSize, QItemSelectionModel
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QInputDialog,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ..config_manager import config_manager
from .. import indexer as nas_indexer
from ..constants import (
    STATUS_COLOR,
    STATUS_LABEL,
    STATUS_MATCHED,
    STATUS_NONE,
    STATUS_PENDING,
    STATUS_UNMATCHED,
)
from .add_project_dialog import AddProjectDialog

# 自然排序：把数字片段拆成 (前缀字符串, 数字 int) 元组，数字按数值而非字典序排
_RE_NATURAL = re.compile(r"(\d+)")


def _natural_key(s: str) -> tuple:
    """自然排序键：6.12 < 7.01 < 10.25（而非字母序 10.25 < 6.12 < 7.01）"""
    parts = _RE_NATURAL.split(s.lower())
    key = []
    for p in parts:
        if p.isdigit():
            key.append((1, int(p)))
        else:
            key.append((0, p))
    return tuple(key)


# ===================================================================
# 项目列表项代理: 状态圆点 + 项目名 + 状态标签, 视觉层次分明
# ===================================================================
class ProjectItemDelegate(QStyledItemDelegate):
    """自画项目列表项:
       [彩色圆点]  项目名(深色)                    状态标签(小字,彩色)
    """
    DOT_R = 4       # 圆点半径
    DOT_GAP = 10    # 圆点与文字间距
    MARGIN = 12     # 左右边距
    LABEL_W = 52    # 右侧状态标签宽度

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        rect = option.rect

        # 1) 背景: 选中 / hover / 普通
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        if selected:
            painter.fillRect(rect, QColor("#DBEAFE"))
        elif hover:
            painter.fillRect(rect, QColor("#F3F4F6"))

        # 2) 读取数据
        name = index.data(Qt.DisplayRole) or ""
        dot_hex = index.data(Qt.UserRole + 1) or "#9CA3AF"
        status_label = index.data(Qt.UserRole + 2) or ""
        path_missing = index.data(Qt.UserRole + 3)

        # 3) 状态圆点 (左侧)
        cx = rect.left() + self.MARGIN + self.DOT_R
        cy = rect.top() + rect.height() // 2
        painter.setBrush(QColor(dot_hex))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRect(cx - self.DOT_R, cy - self.DOT_R,
                                  self.DOT_R * 2, self.DOT_R * 2))

        # 4) 项目名 (深色, 选中时蓝色, 缺失时灰色)
        name_x = cx + self.DOT_R + self.DOT_GAP
        name_w = rect.right() - self.LABEL_W - name_x - self.MARGIN
        if path_missing:
            name_color = QColor("#9CA3AF")
        elif selected:
            name_color = QColor("#1D4ED8")
        else:
            name_color = QColor("#1F2937")
        painter.setPen(name_color)
        painter.setFont(option.font)
        fm = painter.fontMetrics()
        name_text = fm.elidedText(name, Qt.ElideRight, name_w)
        painter.drawText(QRect(name_x, rect.top(), name_w, rect.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, name_text)

        # 5) 状态标签 (右侧, 小字, 状态色)
        if status_label:
            label_color = QColor("#1D4ED8") if selected else QColor(dot_hex)
            painter.setPen(label_color)
            lf = QFont(option.font)
            ps = lf.pointSize()
            if ps and ps > 0:
                lf.setPointSize(max(ps - 1, 8))
            painter.setFont(lf)
            lr = QRect(rect.right() - self.LABEL_W - self.MARGIN,
                       rect.top(), self.LABEL_W, rect.height())
            painter.drawText(lr, Qt.AlignRight | Qt.AlignVCenter, status_label)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(0, 34)


class LeftSidebar(QWidget):
    project_selected = Signal(str)   # 选中项目的 local_name
    refresh_requested = Signal(str)  # 请求重新匹配指定项目；空串表示全部
    projects_changed = Signal()      # 项目增删后通知主窗口

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_items = []  # 先初始化，避免 setCurrentIndex 触发 _apply_filter 时报错
        self._deep_scan_worker = None  # 后台深度扫描线程引用
        self._ascending = config_manager.settings.get("sidebar_sort_asc", True)
        self._build_ui()
        # 恢复用户上次设置的状态筛选 + 排序偏好
        saved_filter = config_manager.settings.get("sidebar_status_filter", 0)
        if 0 <= saved_filter < self.filter.count():
            self.filter.setCurrentIndex(saved_filter)
        saved_sort = config_manager.settings.get("sidebar_sort", 0)
        if 0 <= saved_sort < self.sort_combo.count():
            self.sort_combo.setCurrentIndex(saved_sort)
        self._update_order_btn()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # 标题 + 添加按钮
        top = QHBoxLayout()
        title = QLabel("项目导航")
        title.setStyleSheet("color:#1F2937; font-size:13px; font-weight:500;")
        self.add_btn = QPushButton("添加项目")
        self.add_btn.setToolTip("添加项目文件夹")
        self.add_btn.clicked.connect(self._add_project)
        top.addWidget(title, 1)
        top.addWidget(self.add_btn)
        layout.addLayout(top)

        # 搜索框
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索项目名… (Ctrl+F)")
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        # 状态筛选
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("状态:"))
        self.filter = QComboBox()
        self.filter.addItems(["全部", "已匹配", "待确认", "未匹配", "无匹配项"])
        self.filter.currentIndexChanged.connect(self._apply_filter)
        hbox.addWidget(self.filter, 1)
        layout.addLayout(hbox)

        # 排序
        hsort = QHBoxLayout()
        hsort.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["名称", "修改时间"])
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        hsort.addWidget(self.sort_combo, 1)
        self.order_btn = QPushButton("升序")
        self.order_btn.setFixedWidth(55)
        self.order_btn.setToolTip("点击切换升序 / 降序")
        self.order_btn.clicked.connect(self._toggle_sort_order)
        hsort.addWidget(self.order_btn)
        layout.addLayout(hsort)

        # 列表
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setItemDelegate(ProjectItemDelegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(0)
        self.list.itemClicked.connect(self._on_click)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self.list.installEventFilter(self)
        self.list.setStyleSheet("""
            QListWidget { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:8px; outline:none; }
            QListWidget::item { border:none; padding:0; margin:0; }
        """)
        layout.addWidget(self.list, 1)

        # 统计
        self.stats = QLabel("")
        self.stats.setStyleSheet("color:#6B7280; font-size:11px;")
        layout.addWidget(self.stats)

    def refresh(self):
        """从配置重新加载项目列表，自动清理已删除的文件夹，按用户选择的排序方式 + 升降序排列。"""
        cleaned = config_manager.cleanup_stale_projects()
        sort_idx = self.sort_combo.currentIndex()
        rev = not self._ascending
        if sort_idx == 1:  # 修改时间 —— 用服务器文件夹的 mtime（需求4）
            def time_or_epoch(p):
                sp = p.get("local_name", "")  # 项目以服务器文件夹为锚点，local_name=服务器路径
                try:
                    return nas_indexer.indexer.get_folder_mtime(sp)
                except Exception:  # noqa: BLE001
                    return 0
            key = lambda p: (time_or_epoch(p), _natural_key(self._display_name(p)))
        else:  # 名称 —— 自然排序（按显示名）
            key = lambda p: _natural_key(self._display_name(p))
        self._all_items = sorted(list(config_manager.projects), key=key, reverse=rev)
        self._apply_filter()
        if cleaned:
            self.projects_changed.emit()

    @staticmethod
    def _display_name(p: dict) -> str:
        """项目显示名：优先用可改的 name 字段，缺省回退到服务器文件夹叶子名。"""
        name = (p.get("name") or "").strip()
        if name:
            return name
        return os.path.basename(p.get("local_name", "").rstrip("/\\"))

    def _apply_filter(self):
        text = self.search.text().strip().lower()
        status_idx = self.filter.currentIndex()  # 0全部 1匹配 2待确认 3未匹配 4无匹配项
        want = {
            0: None,
            1: STATUS_MATCHED,
            2: STATUS_PENDING,
            3: STATUS_UNMATCHED,
            4: STATUS_NONE,
        }[status_idx]

        self.list.clear()
        matched = pending = unmatched = none = 0
        for p in self._all_items:
            name = self._display_name(p)
            status = p.get("status", STATUS_UNMATCHED)
            if status == STATUS_MATCHED:
                matched += 1
            elif status == STATUS_PENDING:
                pending += 1
            elif status == STATUS_NONE:
                none += 1
                unmatched += 1  # 与未匹配合并统计，不额外区分
            else:
                unmatched += 1
            if text and text not in name.lower():
                continue
            if want and status != want:
                continue
            # 检查路径是否存在
            lp = p.get("local_path", "")
            path_missing = bool(lp and not os.path.isdir(lp))
            # 代理读取的状态数据
            if path_missing:
                dot_hex = "#EF4444"
                status_label = "缺失"
            else:
                dot_hex = STATUS_COLOR.get(status, "#9CA3AF")
                status_label = STATUS_LABEL.get(status, "")
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, p.get("local_name", ""))  # 内部键（服务器路径），非显示名
            item.setData(Qt.UserRole + 1, dot_hex)       # 圆点颜色
            item.setData(Qt.UserRole + 2, status_label)   # 状态标签文字
            item.setData(Qt.UserRole + 3, path_missing)   # 路径缺失
            self.list.addItem(item)

        total = len(self._all_items)
        if total == 0:
            self.stats.setText("请添加项目")
        else:
            self.stats.setText(
                f"共 {total} 项  |  "
                f"<span style='color:#16A34A'>\u2713</span> {matched}  "
                f"<span style='color:#D97706'>?</span> {pending}  "
                f"<span style='color:#9CA3AF'>\u2014</span> {unmatched}"
            )
        # 保存当前筛选状态+排序偏好到配置（持久化）
        config_manager.settings["sidebar_status_filter"] = self.filter.currentIndex()
        config_manager.settings["sidebar_sort"] = self.sort_combo.currentIndex()
        config_manager.settings["sidebar_sort_asc"] = self._ascending
        config_manager.save()

    def _on_sort_changed(self, _idx: int):
        self.refresh()

    def _toggle_sort_order(self):
        self._ascending = not self._ascending
        self._update_order_btn()
        self.refresh()

    def _update_order_btn(self):
        self.order_btn.setText("升序" if self._ascending else "降序")

    def _on_click(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        if name:
            self.project_selected.emit(name)

    def eventFilter(self, obj, event):
        """拦截 QListWidget 的 Delete 键。"""
        if obj is self.list and event.type() == QEvent.KeyPress:
            kev = event
            if kev.key() == Qt.Key_Delete:
                self._delete_selected()
                return True
        return super().eventFilter(obj, event)

    def _delete_selected(self):
        """删除所有选中的项目（带确认）。"""
        items = self.list.selectedItems()
        if not items:
            return
        names = [it.data(Qt.UserRole) for it in items]
        names = [n for n in names if n]
        if not names:
            return
        if len(names) == 1:
            msg = f"确定从项目列表中删除「{names[0]}」吗？\n\n（仅移除软件记录，不删除磁盘文件）"
        else:
            preview = "\n".join(f"  {n}" for n in names[:10])
            if len(names) > 10:
                preview += f"\n  ... 等共 {len(names)} 项"
            msg = f"确定删除以下 {len(names)} 个项目吗？\n\n{preview}\n\n（仅移除软件记录，不删除磁盘文件）"
        reply = QMessageBox.question(
            self, "确认删除", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        current = self.current_name()
        for name in names:
            config_manager.remove_project(name)
        if current and current in names:
            self.list.clearSelection()
            self.project_selected.emit("")
        self.refresh()
        self.projects_changed.emit()

    def select_first(self):
        if self.list.count() > 0:
            self.list.setCurrentRow(0)
            item = self.list.item(0)
            if item:
                self._on_click(item)

    def current_name(self) -> str:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else ""

    # --------------------------- 增删查改 ---------------------------
    def _add_project(self):
        """添加项目：弹出多选对话框，勾选服务器项目主文件夹，并为每个选择本地目录。"""
        dlg = AddProjectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        selected = dlg.get_results()
        if not selected:
            return
        added, skipped = [], 0
        for server_path, local_path in selected:
            unique_key = server_path or local_path
            if config_manager.get_project(unique_key):
                skipped += 1
                continue
            name = os.path.basename(server_path.rstrip("/\\")) if server_path else os.path.basename(local_path.rstrip("/\\")) if local_path else "仅本地项目"
            project = {
                "local_name": unique_key,
                "name": name,
                "local_path": local_path or "",
                "nas_candidates": [],
                "confirmed_nas_path": server_path,
                "last_sync": "",
                "status": STATUS_MATCHED if server_path else STATUS_NONE,
            }
            config_manager.upsert_project(project)
            added.append(unique_key)
        if skipped:
            QMessageBox.information(
                self, "部分已存在",
                f"已添加 {len(added)} 个项目，跳过 {skipped} 个已在列表中的项目。"
            )
        self.refresh()
        self.projects_changed.emit()
        # 后台深度扫描新加项目的服务器目录（持久引用 + finished 自清，避免线程未结束被回收）
        if added:
            from ..workers import DeepScanWorker
            roots = [sp for sp in added if sp]
            if roots:
                self._deep_scan_worker = DeepScanWorker(roots)
                self._deep_scan_worker.finished.connect(self._deep_scan_worker.deleteLater)
                self._deep_scan_worker.start()
        # 选中第一个新添加的项目
        if added:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) == added[0]:
                    self.list.setCurrentRow(i)
                    self._on_click(self.list.item(i))
                    break

    def _on_context_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        name = item.data(Qt.UserRole)
        if not name:
            return
        proj = config_manager.get_project(name)
        if not proj:
            return
        # 如果右键点击的项不在选中列表中,切换为仅选中该项
        if item not in self.list.selectedItems():
            self.list.selectionModel().select(
                self.list.indexFromItem(item), QItemSelectionModel.ClearAndSelect
            )
        sel_count = len(self.list.selectedItems())
        menu = QMenu(self)
        if sel_count == 1:
            act_open = menu.addAction("在资源管理器打开")
            act_rematch = menu.addAction("重新匹配此项目")
            act_rename = menu.addAction("重命名")
            act_setlocal = menu.addAction("指定本地目录")
        else:
            act_open = None
            act_rematch = None
            act_rename = None
            act_setlocal = None
        menu.addSeparator()
        if sel_count == 1:
            act_delete = menu.addAction("删除项目")
        else:
            act_delete = menu.addAction(f"删除选中的 {sel_count} 个项目")
        action = menu.exec(self.list.mapToGlobal(pos))
        if action == act_open:
            lp = proj.get("local_path", "")
            if lp and os.path.isdir(lp):
                from ..utils import open_in_explorer
                open_in_explorer(lp)
            else:
                QMessageBox.warning(self, "路径不存在", "该项目的本地文件夹已不存在。")
        elif action == act_rematch:
            self.refresh_requested.emit(name)
        elif action == act_rename:
            self._rename_project(name)
        elif action == act_setlocal:
            self._set_local_dir(name)
        elif action == act_delete:
            self._delete_selected()

    def _rename_project(self, key: str):
        """需求3：修改仅软件内显示的 name，绝不触碰磁盘文件。"""
        proj = config_manager.get_project(key)
        if not proj:
            return
        cur = proj.get("name") or os.path.basename(key.rstrip("/\\"))
        new, ok = QInputDialog.getText(
            self, "重命名项目",
            "项目名称（仅软件内显示，不修改任何磁盘文件）:",
            text=cur,
        )
        if not ok or not new.strip():
            return
        proj["name"] = new.strip()
        config_manager.upsert_project(proj)
        self.refresh()
        self.projects_changed.emit()
        # 重新选中（按内部键）
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == key:
                self.list.setCurrentRow(i)
                break

    def _set_local_dir(self, key: str):
        """为项目手动指定/更改本地目录（覆盖自动匹配结果，需求1+2联动）。"""
        proj = config_manager.get_project(key)
        if not proj:
            return
        d = QFileDialog.getExistingDirectory(self, "指定本地项目目录")
        if not d:
            return
        proj["local_path"] = d
        config_manager.upsert_project(proj)
        self.refresh()
        self.projects_changed.emit()
        self.project_selected.emit(key)  # 刷新中/右栏
