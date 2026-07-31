"""
状态栏：封装一个状态文本标签
"""
from PySide6.QtWidgets import QStatusBar, QLabel


class StatusBar(QStatusBar):
    """状态栏（封装 status_label）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_label = QLabel("就绪")
        self.addWidget(self.status_label)
