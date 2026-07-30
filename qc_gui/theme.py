"""
主题管理系统
支持亮色/暗色双主题，提供调色板和样式表热切换。

使用方式:
    from qc_gui.theme import theme_manager
    theme_manager.set_theme("dark")           # 切换到暗色
    theme_manager.toggle()                      # 切换
    qss = theme_manager.get_stylesheet()        # 获取当前主题的完整 QSS
    palette = theme_manager.palette             # 获取当前调色板 dict
"""

from PySide6.QtCore import QObject, Signal


# ──────────────────────── 亮色调色板 (Google Material Light) ────────────────────────
LIGHT_PALETTE = {
    "bg_primary": "#FFFFFF",
    "bg_secondary": "#F5F6FA",
    "bg_card": "#FFFFFF",
    "bg_input": "#F0F1F5",
    "bg_hover": "#E8F0FE",

    "text_primary": "#1A1A2E",
    "text_secondary": "#5F6368",
    "text_tertiary": "#9AA0A6",
    "text_inverse": "#FFFFFF",

    "accent": "#1A73E8",
    "accent_hover": "#1557B0",
    "accent_light": "#E8F0FE",
    "accent_pressed": "#D2E3FC",
    "accent_pressed_dark": "#0D47A1",

    "pass": "#34A853",
    "warning": "#FBBC04",
    "error": "#EA4335",
    "info": "#4285F4",
    "error_hover": "#D93025",

    # 状态背景 + 文字（亮色主题专用浅底深字）
    "pass_bg": "#E6F4EA",
    "pass_text": "#137333",
    "warning_bg": "#FEF7E0",
    "warning_text": "#B06000",
    "error_bg": "#FCE8E6",
    "error_text": "#C5221F",
    "pending_bg": "#E8F0FE",
    "pending_text": "#1A73E8",
    "cancelled_bg": "#F1F3F4",
    "cancelled_text": "#5F6368",

    "border": "#DADCE0",
    "border_light": "#E8EAED",
    "divider": "#E8EAED",

    "shadow": "rgba(0,0,0,0.08)",
}


# ──────────────────────── 暗色调色板 (Catppuccin Mocha inspired) ────────────────────────
DARK_PALETTE = {
    "bg_primary": "#1E1E2E",       # 主背景 (深蓝紫)
    "bg_secondary": "#181825",      # 次背景 (更深)
    "bg_card": "#1E1E2E",          # 卡片背景
    "bg_input": "#313244",         # 输入框
    "bg_hover": "#45475A",          # 悬停

    "text_primary": "#CDD6F4",     # 主文字 (浅蓝白)
    "text_secondary": "#9399B2",   # 次文字
    "text_tertiary": "#6C7086",    # 三级文字
    "text_inverse": "#1E1E2E",     # 反色文字 (深底用)

    "accent": "#89B4FA",           # 强调色 (亮蓝)
    "accent_hover": "#B4BEFE",     # 悬停 (更亮)
    "accent_light": "#313244",     # 浅强调背景
    "accent_pressed": "#45475A",   # 按下
    "accent_pressed_dark": "#1A1A2A",  # 主按钮按下

    "pass": "#A6E3A1",             # 通过 (亮绿)
    "warning": "#F9E2AF",           # 警告 (亮黄)
    "error": "#F38BA8",            # 错误 (亮红)
    "info": "#89B4FA",             # 信息
    "error_hover": "#EBA0AC",      # 错误悬停

    # 状态背景 + 文字（暗色主题专用半透明底亮字）
    "pass_bg": "rgba(166, 227, 161, 0.15)",
    "pass_text": "#A6E3A1",
    "warning_bg": "rgba(249, 226, 175, 0.15)",
    "warning_text": "#F9E2AF",
    "error_bg": "rgba(243, 139, 168, 0.15)",
    "error_text": "#F38BA8",
    "pending_bg": "rgba(137, 180, 250, 0.15)",
    "pending_text": "#89B4FA",
    "cancelled_bg": "rgba(108, 112, 134, 0.15)",
    "cancelled_text": "#9399B2",

    "border": "#45475A",
    "border_light": "#313244",
    "divider": "#313244",

    "shadow": "rgba(0,0,0,0.3)",
}


class ThemeManager(QObject):
    """主题管理器（单例）

    负责管理亮/暗主题切换。切换时：
    1. 更新内部调色板
    2. 同步更新 styles.COLORS（in-place，保持向后兼容）
    3. 发出 theme_changed 信号，由 MainWindow 接收并重新应用 QSS
    """

    theme_changed = Signal(str)  # 参数: "light" | "dark"

    def __init__(self):
        super().__init__()
        self._theme = "light"
        self._palette = LIGHT_PALETTE.copy()

    @property
    def theme(self) -> str:
        """当前主题名: 'light' 或 'dark'"""
        return self._theme

    @property
    def palette(self) -> dict:
        """当前调色板 dict"""
        return self._palette

    @property
    def is_dark(self) -> bool:
        return self._theme == "dark"

    def set_theme(self, name: str):
        """设置主题 ('light' 或 'dark')"""
        name = name.lower()
        if name == self._theme:
            return

        if name == "dark":
            self._theme = "dark"
            self._palette = DARK_PALETTE.copy()
        else:
            self._theme = "light"
            self._palette = LIGHT_PALETTE.copy()

        # 同步更新 styles.COLORS（in-place，所有引用 COLORS 的代码自动生效）
        self._sync_styles_colors()

        self.theme_changed.emit(self._theme)

    def toggle(self):
        """切换亮/暗主题"""
        self.set_theme("dark" if self._theme == "light" else "light")

    def get_stylesheet(self) -> str:
        """生成当前主题的完整 QSS 样式表（含动态箭头 SVG 与复选框勾选图标）"""
        from qc_gui.styles import build_stylesheet, generate_spin_arrows, generate_checkbox_checkmark
        arrow_dir = generate_spin_arrows(self._theme, self._palette)
        checkmark_path = generate_checkbox_checkmark(self._palette)
        return build_stylesheet(self._palette, arrow_dir=arrow_dir, checkbox_checkmark_path=checkmark_path)

    def _sync_styles_colors(self):
        """将当前调色板同步到 styles.COLORS（in-place 更新）"""
        import qc_gui.styles as styles
        styles.COLORS.clear()
        styles.COLORS.update(self._palette)


# ──────────────────────── 模块级单例 ────────────────────────
_instance: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    """获取 ThemeManager 单例"""
    global _instance
    if _instance is None:
        _instance = ThemeManager()
    return _instance
