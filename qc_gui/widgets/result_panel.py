"""
结果面板：检测结果树（文件名/状态/一致性/黑帧/黑边/静音）
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QHeaderView


class ResultPanel(QWidget):
    """中间检测结果面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("cssClass", "card")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 结果树
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels([
            "文件名", "状态", "一致性", "黑帧", "黑边", "静音"
        ])
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.setRootIsDecorated(True)
        self.result_tree.setUniformRowHeights(True)
        self.result_tree.setSortingEnabled(False)

        # 列宽
        self.result_tree.setColumnWidth(0, 200)
        self.result_tree.setColumnWidth(1, 70)
        self.result_tree.setColumnWidth(2, 70)
        # 检测项列等宽
        for col in range(3, 6):
            self.result_tree.setColumnWidth(col, 50)

        # 最后一列自动拉伸
        header = self.result_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.result_tree)
