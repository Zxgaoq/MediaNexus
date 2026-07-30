"""
顶部工具栏：标题 + 多版本对比按钮 + 预设选择器 + 管理预设按钮 + 主题切换按钮
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton


class Toolbar(QWidget):
    """顶部工具栏"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 标题（品牌标识）
        title_label = QLabel("影枢 QC")
        title_label.setProperty("cssClass", "title")
        layout.addWidget(title_label)

        # 多版本对比按钮
        self.btn_multi_version_compare = QPushButton("多版本对比")
        self.btn_multi_version_compare.setToolTip("对比多个版本文件夹内同名视频的基础参数")
        layout.addWidget(self.btn_multi_version_compare)

        layout.addStretch()

        # 主题切换按钮
        self.btn_theme_toggle = QPushButton("🌙")
        self.btn_theme_toggle.setFixedSize(36, 36)
        self.btn_theme_toggle.setToolTip("切换亮/暗主题")
        self.btn_theme_toggle.setProperty("cssClass", "theme-toggle")
        layout.addWidget(self.btn_theme_toggle)

    def update_theme_button(self, theme):
        """根据当前主题更新按钮图标"""
        if theme == "dark":
            self.btn_theme_toggle.setText("☀")
            self.btn_theme_toggle.setToolTip("切换到亮色主题")
        else:
            self.btn_theme_toggle.setText("🌙")
            self.btn_theme_toggle.setToolTip("切换到暗色主题")
