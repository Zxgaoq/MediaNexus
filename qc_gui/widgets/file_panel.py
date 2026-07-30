"""
文件面板：拖放区 + 添加/清空按钮 + 文件列表 + 计数
支持折叠/展开状态切换。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QListWidget,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon

from qc_gui.styles import get_drop_area_stylesheet, generate_panel_icons, COLORS


class FilePanel(QWidget):
    """左侧文件列表面板（支持折叠/展开）"""

    # 信号：面板折叠/展开时发出，供 MainWindow 调整 Splitter
    panel_collapsed = Signal()
    panel_expanded = Signal()

    EXPANDED_MIN_WIDTH = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self.setProperty("cssClass", "card")
        self._panel_icons = generate_panel_icons(COLORS)
        self._build_ui()

    def _build_ui(self):
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setSpacing(10)

        # 标题行：标题 + 计数 + 折叠按钮
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel("📁 文件列表")
        self._header.setProperty("cssClass", "header")
        header_layout.addWidget(self._header)

        header_layout.addStretch()

        self.file_count_label = QLabel("共 0 个文件")
        self.file_count_label.setProperty("cssClass", "text-secondary-xs")
        header_layout.addWidget(self.file_count_label)

        # 折叠按钮（仅展开态可见）— SVG 图标式
        self._collapse_btn = QPushButton()
        self._collapse_btn.setIcon(QIcon(self._panel_icons["collapse"]))
        self._collapse_btn.setIconSize(QSize(16, 16))
        self._collapse_btn.setFixedSize(28, 28)
        self._collapse_btn.setToolTip("折叠文件面板")
        self._collapse_btn.setProperty("cssClass", "icon-btn")
        self._collapse_btn.clicked.connect(self.collapse)
        header_layout.addWidget(self._collapse_btn)

        self._main_layout.addLayout(header_layout)

        # 拖放区域
        self.drop_area = QLabel("  📥\n拖放视频文件/文件夹到此处\n或点击下方按钮添加  ")
        self.drop_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_area.setMinimumHeight(90)
        self.set_drop_state("normal")
        self._main_layout.addWidget(self.drop_area)

        # 按钮组
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_add_files = QPushButton("📄 添加文件")
        btn_layout.addWidget(self.btn_add_files)

        self.btn_add_folder = QPushButton("📂 添加文件夹")
        btn_layout.addWidget(self.btn_add_folder)

        self.btn_clear = QPushButton("🗑 清空")
        self.btn_clear.setProperty("cssClass", "danger")
        btn_layout.addWidget(self.btn_clear)

        self._main_layout.addLayout(btn_layout)

        # 文件列表
        self.file_list_widget = QListWidget()
        self.file_list_widget.setAlternatingRowColors(True)
        self._main_layout.addWidget(self.file_list_widget, 1)

    # ── 折叠 / 展开 ──

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def collapse(self):
        """折叠面板：隐藏所有内容，宽度缩为 0"""
        if self._collapsed:
            return
        self._collapsed = True

        # 隐藏所有内容子组件
        self._header.setVisible(False)
        self.file_count_label.setVisible(False)
        self._collapse_btn.setVisible(False)
        self.drop_area.setVisible(False)
        self.btn_add_files.setVisible(False)
        self.btn_add_folder.setVisible(False)
        self.btn_clear.setVisible(False)
        self.file_list_widget.setVisible(False)

        # 缩小到 0 宽度，让 Splitter 自动分配空间给其他面板
        self.setMinimumWidth(0)
        self.setMaximumWidth(0)

        # 移除 card 样式（折叠态不需要圆角卡片）
        self.setProperty("cssClass", "")
        self.style().unpolish(self)
        self.style().polish(self)

        self.panel_collapsed.emit()

    def expand(self):
        """展开面板：恢复所有内容，恢复可变宽度"""
        if not self._collapsed:
            return
        self._collapsed = False

        # 恢复所有内容子组件
        self._header.setVisible(True)
        self.file_count_label.setVisible(True)
        self._collapse_btn.setVisible(True)
        self.drop_area.setVisible(True)
        self.btn_add_files.setVisible(True)
        self.btn_add_folder.setVisible(True)
        self.btn_clear.setVisible(True)
        self.file_list_widget.setVisible(True)

        # 恢复可变宽度
        self.setMinimumWidth(self.EXPANDED_MIN_WIDTH)
        self.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX

        # 恢复 card 样式
        self.setProperty("cssClass", "card")
        self.style().unpolish(self)
        self.style().polish(self)

        self.panel_expanded.emit()

    def set_drop_state(self, state):
        """切换拖放区样式：'normal' | 'hover'"""
        self.drop_area.setStyleSheet(get_drop_area_stylesheet(state))
