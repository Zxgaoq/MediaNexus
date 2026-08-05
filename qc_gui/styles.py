"""
GUI 样式表
定义全局 UI 样式和颜色主题。

调色板由 gui/theme.py 管理（LIGHT_PALETTE / DARK_PALETTE）。
本模块的 COLORS 是对 LIGHT_PALETTE 的引用，ThemeManager 切换主题时会 in-place 更新它。
build_stylesheet(c) 接受任意调色板生成完整 QSS，供热切换使用。
"""

import os
import tempfile
from pathlib import Path
from qc_gui.theme import LIGHT_PALETTE


# ── 全局颜色常量（初始 = 亮色调色板；ThemeManager 切换时会 in-place 更新此 dict）──
COLORS = LIGHT_PALETTE.copy()


# ── 数字输入框箭头 SVG 生成（QSS 不支持 CSS border 三角形，需用真实图片）──
_SPIN_ARROW_DIR = None
# ── 面板折叠/展开图标 SVG 生成 ──
_PANEL_ICON_DIR = None
# ── 复选框勾选图标 SVG 生成 ──
_CHECKBOX_DIR = None


def _spin_arrow_dir() -> str:
    """返回存放上下箭头 SVG 的临时目录。"""
    global _SPIN_ARROW_DIR
    if _SPIN_ARROW_DIR is None:
        _SPIN_ARROW_DIR = os.path.join(tempfile.gettempdir(), "MediaNexus-QC", "spin-arrows")
    os.makedirs(_SPIN_ARROW_DIR, exist_ok=True)
    return _SPIN_ARROW_DIR


def generate_spin_arrows(theme_name: str, palette: dict) -> str:
    """为当前主题生成上下箭头 SVG，返回所在目录。"""
    arrow_dir = _spin_arrow_dir()
    color = palette.get("text_secondary", "#666")
    # 使用小三角形，10x8 的箭头尺寸
    up_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="8" viewBox="0 0 12 8">\n'
        f'  <polygon points="6,1 11,7 1,7" fill="{color}"/>\n'
        f'</svg>'
    )
    down_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="8" viewBox="0 0 12 8">\n'
        f'  <polygon points="6,7 11,1 1,1" fill="{color}"/>\n'
        f'</svg>'
    )
    with open(os.path.join(arrow_dir, "spin-up.svg"), "w", encoding="utf-8") as f:
        f.write(up_svg)
    with open(os.path.join(arrow_dir, "spin-down.svg"), "w", encoding="utf-8") as f:
        f.write(down_svg)
    return arrow_dir


def _panel_icon_dir() -> str:
    """返回存放面板折叠/展开图标 SVG 的临时目录。"""
    global _PANEL_ICON_DIR
    if _PANEL_ICON_DIR is None:
        _PANEL_ICON_DIR = os.path.join(tempfile.gettempdir(), "MediaNexus-QC", "panel-icons")
    os.makedirs(_PANEL_ICON_DIR, exist_ok=True)
    return _PANEL_ICON_DIR


def generate_panel_icons(palette: dict) -> dict:
    """为当前主题生成面板折叠/展开图标 SVG，返回 {name: path} 映射。

    生成以下图标：
    - collapse: 左箭头 chevron（文件面板标题栏折叠按钮）
    - expand: 右箭头 chevron（折叠态展开按钮）
    - expand-strip: 文件图标（折叠态竖条展开按钮，与"展开"文字搭配）
    - folder: 文件夹图标（展开竖条上的文件图标）
    """
    icon_dir = _panel_icon_dir()
    color = palette.get("text_secondary", "#666")
    accent = palette.get("accent", "#1A73E8")
    text_inverse = palette.get("text_inverse", "#FFFFFF")

    # 左箭头 chevron（折叠按钮）— 20x20，粗线条
    collapse_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">\n'
        f'  <polyline points="12,4 6,10 12,16" fill="none" stroke="{color}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'</svg>'
    )
    # 右箭头 chevron（展开按钮）— 20x20，粗线条
    expand_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">\n'
        f'  <polyline points="8,4 14,10 8,16" fill="none" stroke="{accent}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'</svg>'
    )
    # 文件夹图标（展开竖条）— 28x28，描边风格，使用 inverse 色在 hover 时可见
    folder_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" '
        f'fill="none" stroke="{accent}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">\n'
        f'  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>\n'
        f'</svg>'
    )
    # 文件夹图标（hover 反色版）— 使用 inverse 色填充
    folder_hover_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" '
        f'fill="none" stroke="{text_inverse}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">\n'
        f'  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>\n'
        f'</svg>'
    )

    paths = {}
    for name, svg in [
        ("collapse", collapse_svg),
        ("expand", expand_svg),
        ("folder", folder_svg),
        ("folder-hover", folder_hover_svg),
    ]:
        filepath = os.path.join(icon_dir, f"panel-{name}.svg")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(svg)
        paths[name] = filepath

    return paths


def _checkbox_dir() -> str:
    """返回存放复选框勾选图标 SVG 的临时目录。"""
    global _CHECKBOX_DIR
    if _CHECKBOX_DIR is None:
        _CHECKBOX_DIR = os.path.join(tempfile.gettempdir(), "MediaNexus-QC", "checkbox-icons")
    os.makedirs(_CHECKBOX_DIR, exist_ok=True)
    return _CHECKBOX_DIR


def generate_checkbox_checkmark(palette: dict) -> str:
    """为当前主题生成复选框勾选图标 SVG，返回文件路径。

    使用主题强调色绘制对勾，保持背景透明，勾选态只显示边框 + 对勾。
    """
    icon_dir = _checkbox_dir()
    color = palette.get("accent", "#1A73E8")
    # 16x16 viewBox，对勾路径居中
    check_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">\n'
        f'  <polyline points="3.5,8 6.5,11.5 12.5,4.5" fill="none" stroke="{color}" '
        f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'</svg>'
    )
    filepath = os.path.join(icon_dir, "checkbox-check.svg")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(check_svg)
    return filepath


def build_stylesheet(c, arrow_dir=None, checkbox_checkmark_path=None):
    """根据调色板 dict c 生成完整 QSS 样式表。

    c 必须包含 LIGHT_PALETTE / DARK_PALETTE 中定义的所有 key。
    arrow_dir: 存放 spin-up.svg / spin-down.svg 的目录；不传则不生成箭头样式。
    checkbox_checkmark_path: 复选框勾选图标路径；不传则勾选态沿用背景填充。
    """
    arrow_up = ""
    arrow_down = ""
    if arrow_dir:
        arrow_up = Path(arrow_dir, "spin-up.svg").as_posix()
        arrow_down = Path(arrow_dir, "spin-down.svg").as_posix()
        spin_arrow_qss = f"""
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url("{arrow_up}");
            width: 12px;
            height: 8px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url("{arrow_down}");
            width: 12px;
            height: 8px;
        }}
        """
    else:
        spin_arrow_qss = ""

    checkbox_checked_qss = ""
    if checkbox_checkmark_path:
        checkbox_checked_qss = f"""
        QCheckBox::indicator:checked {{
            background-color: {c["bg_input"]};
            border-color: {c["accent"]};
            image: url("{Path(checkbox_checkmark_path).as_posix()}");
        }}
        """

    return f"""
/* 全局基础 */
QWidget {{
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {c["text_primary"]};
    background-color: {c["bg_primary"]};
}}

/* 主窗口 */
QMainWindow {{
    background-color: {c["bg_secondary"]};
}}

/* 菜单栏 */
QMenuBar {{
    background-color: {c["bg_primary"]};
    border-bottom: 1px solid {c["border"]};
    padding: 2px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {c["accent_light"]};
}}

/* 工具栏 */
QToolBar {{
    background-color: {c["bg_primary"]};
    border-bottom: 1px solid {c["border_light"]};
    spacing: 8px;
    padding: 4px 12px;
}}

/* 按钮 */
QPushButton {{
    background-color: {c["bg_input"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
    min-height: 20px;
}}
QPushButton:hover {{
    background-color: {c["bg_hover"]};
    border-color: {c["accent"]};
}}
QPushButton:pressed {{
    background-color: {c["accent_pressed"]};
}}
QPushButton:disabled {{
    background-color: {c["bg_input"]};
    color: {c["text_tertiary"]};
    border-color: {c["border_light"]};
}}

QPushButton[cssClass="primary"] {{
    background-color: {c["accent"]};
    color: {c["text_inverse"]};
    border: none;
    font-weight: 600;
    padding: 8px 20px;
}}
QPushButton[cssClass="primary"]:hover {{
    background-color: {c["accent_hover"]};
}}
QPushButton[cssClass="primary"]:pressed {{
    background-color: {c["accent_pressed_dark"]};
}}
QPushButton[cssClass="primary"]:disabled {{
    background-color: {c["text_tertiary"]};
}}

QPushButton[cssClass="danger"] {{
    background-color: {c["error"]};
    color: {c["text_inverse"]};
    border: none;
}}
QPushButton[cssClass="danger"]:hover {{
    background-color: {c["error_hover"]};
}}

/* 主题切换按钮（36x36 圆形小按钮） */
QPushButton[cssClass="theme-toggle"] {{
    background-color: {c["bg_input"]};
    border: 1px solid {c["border"]};
    border-radius: 18px;
    padding: 0px;
    font-size: 18px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
}}
QPushButton[cssClass="theme-toggle"]:hover {{
    background-color: {c["accent_light"]};
    border-color: {c["accent"]};
}}

/* 图标式按钮（28x28 圆角，用于折叠按钮等） */
QPushButton[cssClass="icon-btn"] {{
    background-color: transparent;
    border: 1px solid {c["border_light"]};
    border-radius: 14px;
    padding: 0px;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}}
QPushButton[cssClass="icon-btn"]:hover {{
    background-color: {c["accent_light"]};
    border-color: {c["accent"]};
}}
QPushButton[cssClass="icon-btn"]:pressed {{
    background-color: {c["accent_pressed"]};
}}

/* 文件面板展开按钮（折叠态时显示的图标式竖条） */
QWidget[cssClass="expand-strip"] {{
    background-color: {c["bg_card"]};
    border: 2px solid {c["accent"]};
    border-radius: 10px;
    padding: 4px;
    min-width: 48px;
    max-width: 48px;
    min-height: 72px;
    max-height: 72px;
}}
QWidget[cssClass="expand-strip"]:hover {{
    background-color: {c["accent_light"]};
    border-color: {c["accent"]};
}}
QWidget[cssClass="expand-strip"] QLabel {{
    background-color: transparent;
    color: {c["accent"]};
    font-size: 10px;
    font-weight: 600;
    padding: 0px;
}}
QWidget[cssClass="expand-strip"]:hover QLabel {{
    color: {c["accent_hover"]};
}}

/* 标签 */
QLabel[cssClass="title"] {{
    font-size: 18px;
    font-weight: 700;
    color: {c["text_primary"]};
}}
QLabel[cssClass="subtitle"] {{
    font-size: 14px;
    font-weight: 600;
    color: {c["text_secondary"]};
}}
QLabel[cssClass="text-secondary-xs"] {{
    color: {c["text_secondary"]};
    font-size: 11px;
}}
QLabel[cssClass="text-secondary"] {{
    color: {c["text_secondary"]};
    font-size: 12px;
}}
QLabel[cssClass="title-md"] {{
    font-size: 16px;
    font-weight: 700;
    color: {c["text_primary"]};
}}
QListWidget[cssClass="drop-target"] {{
    border: 1.5px dashed {c["border"]};
    border-radius: 6px;
    background-color: {c["bg_card"]};
}}
QListWidget[cssClass="drop-target"]:hover {{
    border-color: {c["accent"]};
    background-color: {c["accent_light"]};
}}
QLabel[cssClass="header"] {{
    font-size: 15px;
    font-weight: 600;
    color: {c["text_primary"]};
}}

/* 输入框 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {c["bg_input"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 3px 6px;
    min-height: 20px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {c["accent"]};
    background-color: {c["bg_primary"]};
}}

/* 表格 */
QTableWidget {{
    background-color: {c["bg_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    gridline-color: {c["border_light"]};
    selection-background-color: {c["accent_light"]};
    selection-color: {c["text_primary"]};
}}
QTableWidget::item {{
    padding: 6px 10px;
}}
QHeaderView::section {{
    background-color: {c["bg_secondary"]};
    border: none;
    border-bottom: 2px solid {c["border"]};
    padding: 10px;
    font-weight: 600;
    font-size: 12px;
    color: {c["text_secondary"]};
}}

/* 滚动条 */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c["border"]};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c["text_tertiary"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {c["border"]};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c["text_tertiary"]};
}}
QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {{
    height: 0px;
    border: none;
    background: transparent;
}}
QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal {{
    width: 0px;
    border: none;
    background: transparent;
}}
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {{
    width: 0px;
    height: 0px;
    border: none;
    image: none;
}}
QScrollBar::sub-page, QScrollBar::add-page {{
    background: transparent;
}}
QAbstractScrollArea::corner {{
    background: transparent;
}}

/* 进度条 */
QProgressBar {{
    border: none;
    border-radius: 5px;
    background-color: {c["bg_input"]};
    min-height: 14px;
    max-height: 18px;
    text-align: center;
    font-size: 11px;
    font-weight: 500;
}}
QProgressBar::chunk {{
    background-color: {c["accent"]};
    border-radius: 5px;
}}

/* 分组框 */
QGroupBox {{
    font-weight: 600;
    border: 1px solid {c["border_light"]};
    border-radius: 10px;
    margin-top: 16px;
    padding: 20px 16px 16px 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {c["text_secondary"]};
}}

/* 标签页 */
QTabWidget::pane {{
    border: 1px solid {c["border"]};
    border-radius: 8px;
    background-color: {c["bg_primary"]};
}}
QTabBar::tab {{
    background: {c["bg_secondary"]};
    padding: 10px 20px;
    border: 1px solid {c["border_light"]};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {c["bg_primary"]};
    border-bottom: 2px solid {c["accent"]};
}}
QTabBar::tab:hover {{
    background: {c["accent_light"]};
}}

/* 列表框 */
QListWidget {{
    border: 1px solid {c["border"]};
    border-radius: 8px;
    background-color: {c["bg_primary"]};
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid {c["border_light"]};
}}
QListWidget::item:hover {{
    background-color: {c["bg_hover"]};
}}
QListWidget::item:selected {{
    background-color: {c["accent_light"]};
    color: {c["text_primary"]};
}}

/* 树控件 */
QTreeWidget {{
    background-color: {c["bg_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    outline: none;
}}
QTreeWidget::item {{
    padding: 4px 8px;
    border-bottom: 1px solid {c["border_light"]};
}}
QTreeWidget::item:hover {{
    background-color: {c["bg_hover"]};
}}
QTreeWidget::item:selected {{
    background-color: {c["accent_light"]};
    color: {c["text_primary"]};
}}

/* 提示框 */
QToolTip {{
    background-color: {c["text_primary"]};
    color: {c["text_inverse"]};
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}}

/* 卡片容器 */
QWidget[cssClass="card"] {{
    background-color: {c["bg_card"]};
    border: 1px solid {c["border_light"]};
    border-radius: 12px;
    padding: 16px;
}}

/* 状态指示器 */
QWidget[cssClass="status-pass"] {{
    background-color: {c["pass_bg"]};
    border-radius: 12px;
}}
QWidget[cssClass="status-warning"] {{
    background-color: {c["warning_bg"]};
    border-radius: 12px;
}}
QWidget[cssClass="status-error"] {{
    background-color: {c["error_bg"]};
    border-radius: 12px;
}}

/* 分割线 */
QFrame[cssClass="divider"] {{
    background-color: {c["divider"]};
    max-height: 1px;
}}

/* 消息框 */
QMessageBox {{
    background-color: {c["bg_primary"]};
}}
QMessageBox QLabel {{
    color: {c["text_primary"]};
}}

/* 对话框 */
QDialog {{
    background-color: {c["bg_primary"]};
}}

/* 文本编辑 */
QTextEdit, QPlainTextEdit {{
    background-color: {c["bg_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    color: {c["text_primary"]};
}}

/* 分割器手柄 */
QSplitter::handle {{
    background-color: {c["border_light"]};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
}}

/* 交替行颜色 */
QListWidget {{
    alternate-background-color: {c["bg_secondary"]};
}}
QTreeWidget {{
    alternate-background-color: {c["bg_secondary"]};
}}
QTableWidget {{
    alternate-background-color: {c["bg_secondary"]};
}}

/* 右键菜单 / 下拉菜单 */
QMenu {{
    background-color: {c["bg_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 0px;
    padding: 0px;
}}
QMenu::item {{
    padding: 8px 24px;
    border-radius: 0px;
    color: {c["text_primary"]};
}}
QMenu::item:selected {{
    background-color: {c["accent_light"]};
    color: {c["text_primary"]};
}}
QMenu::separator {{
    height: 1px;
    background-color: {c["border_light"]};
    margin: 4px 8px;
}}

/* 下拉框弹出列表 */
QComboBox QAbstractItemView {{
    background-color: {c["bg_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {c["accent_light"]};
    selection-color: {c["text_primary"]};
    outline: none;
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

/* 数字输入框上下按钮 */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    background-color: {c["bg_input"]};
    border: 1px solid {c["border_light"]};
    border-radius: 3px;
    width: 20px;
    subcontrol-position: top right;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {c["bg_input"]};
    border: 1px solid {c["border_light"]};
    border-radius: 3px;
    width: 20px;
    subcontrol-position: bottom right;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
    background-color: {c["accent_light"]};
    border-color: {c["accent"]};
}}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {c["accent_light"]};
    border-color: {c["accent"]};
}}
{spin_arrow_qss}
/* 复选框 / 单选按钮 */
QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {c["text_primary"]};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {c["border"]};
    border-radius: 4px;
    background-color: {c["bg_input"]};
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QRadioButton::indicator:checked {{
    background-color: {c["accent"]};
    border-color: {c["accent"]};
}}
{checkbox_checked_qss}

/* 树控件表头 */
QTreeWidget::header {{
    background-color: {c["bg_secondary"]};
    border: none;
    border-bottom: 2px solid {c["border"]};
    padding: 8px;
    font-weight: 600;
    font-size: 12px;
    color: {c["text_secondary"]};
}}
QTreeWidget::header::section {{
    background-color: {c["bg_secondary"]};
    border: none;
    border-right: 1px solid {c["border_light"]};
    padding: 8px 6px;
    font-weight: 600;
    font-size: 12px;
    color: {c["text_secondary"]};
}}
"""


# ── 向后兼容：模块加载时用亮色生成全局样式表 ──
_LIGHT_ARROW_DIR = generate_spin_arrows("light", LIGHT_PALETTE)
_LIGHT_CHECKMARK_PATH = generate_checkbox_checkmark(LIGHT_PALETTE)
GLOBAL_STYLESHEET = build_stylesheet(COLORS, arrow_dir=_LIGHT_ARROW_DIR, checkbox_checkmark_path=_LIGHT_CHECKMARK_PATH)


def get_status_style(status):
    """根据状态获取样式（使用 COLORS 调色板，主题切换后自动适配）"""
    styles = {
        "pass": {
            "bg": COLORS["pass_bg"],
            "text": COLORS["pass_text"],
            "border": COLORS["pass"],
            "icon": "✅",
            "label": "通过",
        },
        "warning": {
            "bg": COLORS["warning_bg"],
            "text": COLORS["warning_text"],
            "border": COLORS["warning"],
            "icon": "⚠️",
            "label": "警告",
        },
        "error": {
            "bg": COLORS["error_bg"],
            "text": COLORS["error_text"],
            "border": COLORS["error"],
            "icon": "❌",
            "label": "错误",
        },
        "fail": {
            "bg": COLORS["error_bg"],
            "text": COLORS["error_text"],
            "border": COLORS["error"],
            "icon": "❌",
            "label": "不合格",
        },
        "pending": {
            "bg": COLORS["pending_bg"],
            "text": COLORS["pending_text"],
            "border": COLORS["info"],
            "icon": "🔄",
            "label": "待检测",
        },
        "cancelled": {
            "bg": COLORS["cancelled_bg"],
            "text": COLORS["cancelled_text"],
            "border": COLORS["text_tertiary"],
            "icon": "⏹",
            "label": "已取消",
        },
    }
    return styles.get(status, styles["pending"])


# 拖放区样式（替代 main_window 中的内联 setStyleSheet）
def get_drop_area_stylesheet(state="normal"):
    """返回拖放区域的 QSS。state: 'normal' | 'hover'"""
    if state == "hover":
        return f"""
            QLabel {{
                border: 2px dashed {COLORS['accent']};
                border-radius: 10px;
                background-color: {COLORS['accent_light']};
                color: {COLORS['accent']};
                padding: 20px;
            }}
        """
    return f"""
        QLabel {{
            border: 2px dashed {COLORS['border']};
            border-radius: 10px;
            background-color: {COLORS['bg_secondary']};
            color: {COLORS['text_tertiary']};
            padding: 20px;
        }}
    """
