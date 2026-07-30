# -*- coding: utf-8 -*-
"""
MediaNexus - 常量与默认配置
集中管理所有可调参数、状态枚举、默认忽略词等，便于统一维护。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ----------------------------- 应用元信息 -----------------------------
APP_NAME = "影枢"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Zxgaoq"

# --------------------- SpinBox 箭头（运行时生成，兼容打包） ---------------------
# PyInstaller onedir 模式下 Qt 样式表里的相对文件路径会失效，且 data: URI
# 在部分 Qt 版本 / 平台组合下不稳定。改为在 import 时把箭头 SVG 写到临时目录，
# 样式表里引用绝对路径，开发态 / 打包态都 100% 可用。
_SPIN_ARROW_DIR = os.path.join(tempfile.gettempdir(), "MediaNexus", "spin-arrows")
os.makedirs(_SPIN_ARROW_DIR, exist_ok=True)
_SPIN_UP_PATH = os.path.join(_SPIN_ARROW_DIR, "spin_up.svg")
_SPIN_DOWN_PATH = os.path.join(_SPIN_ARROW_DIR, "spin_down.svg")
if not os.path.isfile(_SPIN_UP_PATH):
    with open(_SPIN_UP_PATH, "w", encoding="utf-8") as _f:
        _f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6">\n'
            '  <path d="M0,6 L5,0 L10,6 Z" fill="#1F2937"/>\n</svg>'
        )
if not os.path.isfile(_SPIN_DOWN_PATH):
    with open(_SPIN_DOWN_PATH, "w", encoding="utf-8") as _f:
        _f.write(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6">\n'
            '  <path d="M0,0 L5,6 L10,0 Z" fill="#1F2937"/>\n</svg>'
        )
# Qt 样式表 url() 需要正斜杠路径
_SPIN_UP_URL = _SPIN_UP_PATH.replace("\\", "/")
_SPIN_DOWN_URL = _SPIN_DOWN_PATH.replace("\\", "/")

# 配置 / 索引 存储目录：默认放在 %APPDATA% 下，避免污染项目目录，
# 同时保证中文用户名路径不出现乱码（使用 Path 而非字符串拼接）。
# 统一以产品名 "MediaNexus" 为目录名（与安装包品牌一致）。
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "MediaNexus"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILENAME = "config.json"
CONFIG_PATH = CONFIG_DIR / CONFIG_FILENAME

INDEX_DB_FILENAME = "nas_index.db"
INDEX_DB_PATH = CONFIG_DIR / INDEX_DB_FILENAME

# ----------------------------- 匹配相关默认值 -----------------------------
# 默认匹配阈值（0-100）：低于该分数的候选不会进入「已匹配」状态。
DEFAULT_MATCH_THRESHOLD = 80

# 名称归一化时，自动去除的常见后缀 / 版本干扰（匹配前剥离，再比对）。
DEFAULT_STRIP_SUFFIXES = [
    "_剪辑版", "_剪辑", "_精剪", "_终版", "_最终版", "_成片版", "_成片",
    "_出品版", "_送审版", "_网版", "_电视版", "_竖屏版", "_横屏版",
    "_v1", "_v2", "_v3", "_V1", "_V2", "_V3",
    "_final", "_Final", "_FIN", "_new", "_NEW", "_new2", "_bak", "_BAK",
    "(1)", "(2)", "(3)", "副本", "_副本", "_copy", "_COPY",
    "_2023", "_2024", "_2025", "_2026",
    "-final", "-Final", " - 副本",
]

# 扫描索引时跳过的文件夹 / 文件关键词（大小写不敏感）。
# 默认空列表——用户按需自行添加。
DEFAULT_IGNORE_PATTERNS: list[str] = []

# 单文件夹懒加载每批拉取的文件数（虚拟滚动分页大小）。
PAGE_SIZE = 500

# ----------------------------- 显示 / 缩略图 -----------------------------
# 列表模式图标尺寸 / 网格（缩略图）模式图标尺寸（像素）。
ICON_SIZE_LIST = 22
ICON_SIZE_GRID = 96

# 网格模式单元尺寸（略大于图标，容纳文件名两行）。
GRID_CELL_W = 128
GRID_CELL_H = 132

# 生成缩略图的最大文件数上限（防止一次性加载海量图片拖垮内存）。
THUMBNAIL_MAX_COUNT = 400

# 可生成缩略图预览的图片扩展名（小写，含点）。
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
    ".tif", ".tiff", ".ico", ".jfif",
}

# 视图模式枚举。
VIEW_LIST = "list"
VIEW_GRID = "grid"

# 索引遍历时最大并发 scandir 数（避免一次性打爆 NAS）。
MAX_CONCURRENCY = 4

# NAS 访问断连自动重试次数与间隔（毫秒）。
NAS_RETRY_TIMES = 3
NAS_RETRY_INTERVAL_MS = 1500

# ----------------------------- Worker 线程管理 -----------------------------
# closeEvent / stop 时等待 Worker 线程退出的超时（毫秒）。
WORKER_WAIT_TIMEOUT_MS = 2000

# ----------------------------- 项目状态枚举 -----------------------------
STATUS_MATCHED = "matched"      # 已匹配
STATUS_PENDING = "pending"      # 待确认
STATUS_UNMATCHED = "unmatched"  # 未匹配
STATUS_NONE = "none"            # 无匹配项（未选择服务器目录）

# 状态图标
STATUS_ICON = {
    STATUS_MATCHED: "\u2713",    # ✓
    STATUS_PENDING: "?",         # ?
    STATUS_UNMATCHED: "\u2014",  # —
    STATUS_NONE: "\u2014",       # —
}

STATUS_COLOR = {
    STATUS_MATCHED: "#16A34A",
    STATUS_PENDING: "#D97706",
    STATUS_UNMATCHED: "#9CA3AF",
    STATUS_NONE: "#9CA3AF",
}

STATUS_LABEL = {
    STATUS_MATCHED: "已匹配",
    STATUS_PENDING: "待确认",
    STATUS_UNMATCHED: "未匹配",
    STATUS_NONE: "无匹配项",
}

# ----------------------------- UI 配色（白色专业主题） -----------------------------
STYLESHEET = """
QWidget {
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 12px;
    color: #1F2937;
    background-color: #FFFFFF;
}
QMainWindow, QDialog { background-color: #FFFFFF; }
QLabel { color: #1F2937; background: transparent; }

/* ===== 列表控件 ===== */
QListWidget, QListView, QTreeWidget {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    outline: none;
}
QListWidget::item, QListView::item {
    padding: 5px 10px;
    border: none;
    border-radius: 6px;
}
QListWidget::item:hover, QListView::item:hover { background-color: #F3F4F6; }
QListWidget::item:selected, QListView::item:selected {
    background-color: #DBEAFE;
    color: #1D4ED8;
}

/* ===== 按钮 ===== */
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 5px 14px;
    color: #374151;
}
QPushButton:hover { background-color: #F9FAFB; border-color: #9CA3AF; }
QPushButton:pressed { background-color: #F3F4F6; }
QPushButton:disabled { color: #9CA3AF; border-color: #E5E7EB; background: #F9FAFB; }
QPushButton#primary {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #2563EB;
}
QPushButton#primary:hover { background-color: #1D4ED8; border-color: #1D4ED8; }
QPushButton#danger {
    background-color: #FFFFFF;
    color: #DC2626;
    border: 1px solid #FCA5A5;
}
QPushButton#danger:hover { background-color: #FEF2F2; border-color: #DC2626; }

/* ===== 输入框 & 下拉 ===== */
QLineEdit, QComboBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 4px 8px;
    color: #1F2937;
    selection-background-color: #DBEAFE;
    selection-color: #1D4ED8;
}
QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    color: #1F2937;
    min-height: 26px;
    padding-right: 24px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #E5E7EB;
    border-bottom: 1px solid #E5E7EB;
    border-top-right-radius: 6px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    border-left: 1px solid #E5E7EB;
    border-bottom-right-radius: 6px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSI2IiB2aWV3Qm94PSIwIDAgMTAgNiI+CiAgPHBhdGggZD0iTTAsNiBMNSwwIEwxMCw2IFoiIGZpbGw9IiMxRjI5MzciLz4KPC9zdmc+);
    width: 10px;
    height: 6px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSI2IiB2aWV3Qm94PSIwIDAgMTAgNiI+CiAgPHBhdGggZD0iTTAsMCBMNSw2IEwxMCwwIFoiIGZpbGw9IiMxRjI5MzciLz4KPC9zdmc+);
    width: 10px;
    height: 6px;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #2563EB; }
QLineEdit::placeholder { color: #9CA3AF; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    selection-background-color: #DBEAFE;
    selection-color: #1D4ED8;
    color: #1F2937;
}

/* ===== 状态栏 ===== */
QStatusBar {
    background-color: #F9FAFB;
    border-top: 1px solid #E5E7EB;
    color: #6B7280;
    font-size: 11px;
    padding: 2px 8px;
}

/* ===== 进度条 ===== */
QProgressBar {
    background-color: #E5E7EB;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk { background-color: #2563EB; border-radius: 4px; }

/* ===== 滚动条 ===== */
QScrollBar:vertical {
    background: transparent; width: 8px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #D1D5DB; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #9CA3AF; }
QScrollBar:horizontal { background: transparent; height: 8px; }
QScrollBar::handle:horizontal { background: #D1D5DB; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #9CA3AF; }

/* ===== 分割器 ===== */
QSplitter::handle { background: #E5E7EB; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }
QSplitter::handle:hover { background: #93C5FD; }

/* ===== 菜单栏 ===== */
QMenuBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
    color: #374151;
    padding: 2px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected { background-color: #F3F4F6; }
QMenuBar::item:pressed { background-color: #E5E7EB; }

/* ===== 菜单 ===== */
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 4px;
    color: #1F2937;
}
QMenu::item { padding: 5px 24px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background-color: #F3F4F6; }
QMenu::separator { height: 1px; background: #F3F4F6; margin: 4px 8px; }

/* ===== 提示 ===== */
QToolTip {
    background-color: #1F2937;
    border: none;
    border-radius: 6px;
    padding: 5px 10px;
    color: #FFFFFF;
}
"""

# 将箭头 url 从 data: URI 替换为运行时生成的绝对路径（开发/打包都可用）
STYLESHEET = STYLESHEET.replace(
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSI2IiB2aWV3Qm94PSIwIDAgMTAgNiI+CiAgPHBhdGggZD0iTTAsNiBMNSwwIEwxMCw2IFoiIGZpbGw9IiMxRjI5MzciLz4KPC9zdmc+",
    _SPIN_UP_URL,
)
STYLESHEET = STYLESHEET.replace(
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSI2IiB2aWV3Qm94PSIwIDAgMTAgNiI+CiAgPHBhdGggZD0iTTAsMCBMNSw2IEwxMCwwIFoiIGZpbGw9IiMxRjI5MzciLz4KPC9zdmc+",
    _SPIN_DOWN_URL,
)
