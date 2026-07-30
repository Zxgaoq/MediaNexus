"""
底部控制栏：进度条 + 线程数 + 开始/取消/导出
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QSpinBox, QPushButton,
)
from PySide6.QtCore import Qt


class BottomBar(QWidget):
    """底部控制栏"""

    def __init__(self, default_threads=4, parent=None):
        super().__init__(parent)
        self._default_threads = default_threads
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat(" %p% ")
        layout.addWidget(self.progress_bar, 1)

        # 线程数
        thread_label = QLabel("线程:")
        layout.addWidget(thread_label)

        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 16)
        self.thread_spin.setValue(self._default_threads)
        self.thread_spin.setFixedWidth(100)
        self.thread_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.thread_spin)

        # 分隔
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background-color: rgba(128,128,128,0.2);")
        layout.addWidget(sep)

        # 按钮
        self.btn_start = QPushButton("▶ 开始")
        self.btn_start.setProperty("cssClass", "primary")
        self.btn_start.setMinimumWidth(96)
        layout.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("⏹ 取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumWidth(72)
        layout.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("📥 导出")
        self.btn_export.setEnabled(False)
        self.btn_export.setMinimumWidth(80)
        layout.addWidget(self.btn_export)
