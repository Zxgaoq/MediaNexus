"""
详情面板：元数据 / 一致性对比 / 异常详情 / 运行日志 四个标签页
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTreeWidget, QTableWidget,
    QTextEdit, QPlainTextEdit, QHeaderView,
)


class DetailPanel(QWidget):
    """右侧详情与日志面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("cssClass", "card")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.detail_tabs = QTabWidget()

        # 元数据标签页
        self.metadata_tab = QTreeWidget()
        self.metadata_tab.setHeaderLabels(["参数", "值"])
        self.metadata_tab.setAlternatingRowColors(True)
        self.metadata_tab.setColumnWidth(0, 150)
        self.metadata_tab.header().setStretchLastSection(True)
        self.detail_tabs.addTab(self.metadata_tab, "📋 元数据")

        # 一致性对比标签页（表格形式）
        self.consistency_tab = QTableWidget()
        self.consistency_tab.setAlternatingRowColors(True)
        self.detail_tabs.addTab(self.consistency_tab, "📐 一致性")

        # 异常详情标签页
        self.anomaly_tab = QTextEdit()
        self.anomaly_tab.setReadOnly(True)
        self.detail_tabs.addTab(self.anomaly_tab, "⚠ 异常详情")

        # 日志标签页（QPlainTextEdit 性能更好，支持最大行数限制）
        self.log_tab = QPlainTextEdit()
        self.log_tab.setReadOnly(True)
        self.log_tab.setMaximumBlockCount(500)
        self.detail_tabs.addTab(self.log_tab, "📝 运行日志")

        layout.addWidget(self.detail_tabs)
