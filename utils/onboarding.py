# -*- coding: utf-8 -*-
"""
首次启动引导（Onboarding）—— 两步向导。

第 1 步：选择「项目管理方式」（与「设置」页同一 project_mode 键）。
第 2 步：根据所选方式，给出差异化的「导入项目 / 管理项目」细致用法提示。

选完写入 config_manager.project_mode + onboarding_done。引导只在第一次出现
（onboarding_done 标记位于 %APPDATA%，重装/再次打开不再弹）。
"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from MediaNexus.config_manager import config_manager
from MediaNexus.constants import APP_NAME
from MediaNexus.utils import resource_path


# 三种模式定义，必须与 settings_dialog 中的 radio 完全一致
MODES = [
    {
        "key": "both",
        "title": "本地 + 服务器双索引",
        "desc": "自动模糊匹配本地与服务器同名项目，功能最完整（推荐）。",
        "icon": "🔗",
    },
    {
        "key": "local_only",
        "title": "仅本地",
        "desc": "只管理本机上的项目文件，不连接服务器。",
        "icon": "💻",
    },
    {
        "key": "server_only",
        "title": "仅服务器",
        "desc": "只管理服务器上的项目素材，本地不做镜像。",
        "icon": "☁️",
    },
]

# 应用主色（与关于框 / 手册一致）
ACCENT = "#2563EB"
ACCENT_SOFT = "#EFF4FF"
BORDER = "#E5E7EB"
MUTED = "#6B7280"
CHECK_OFF = "#9CA3AF"
SECTION = "#2563EB"


# 第二步：按模式细分的「导入项目 / 管理项目 / 快捷键」提示
GUIDANCE = {
    "both": {
        "import": [
            "打开「设置 → 项目」，在【本地项目根目录】处点击「添加」填入你本机的项目总目录（可添加多个）。",
            "在同一页的【服务器(NAS)根目录】处添加服务器/NAS 上的素材总目录（同样可多个，支持 UNC 路径如 \\\\server\\share）。",
            "添加后软件会在后台自动对两边目录做模糊匹配，把同名/相似项目在「左(本地) — 右(服务器)」两栏中关联起来。",
            "若自动匹配不准，可在左侧项目导航里右键该项目 →「指定本地目录 / 指定服务器目录」手动绑定，或右键 →「重新匹配」重算候选。",
        ],
        "manage": [
            "三栏布局：左=项目导航，中=本地内容，右=服务器匹配内容。双击文件夹进入子目录，顶部「上级」按钮返回上层。",
            "匹配完成后，右键项目可：重新匹配、重命名、指定本地目录、删除。",
            "文件操作：直接拖放复制/移动文件，跨左/右栏拖放会自动复制；右键支持复制/剪切/粘贴/删除/重命名/新建/刷新。",
            "服务器索引：目录添加后会先快速扫描、再后台深度扫描建索引；在「设置」开启「心跳自动刷新」并设置间隔(秒)，增量刷新不阻塞你的操作。",
            "需要质检时：右键文件或文件夹直接发起 QC 检测（黑帧/夹帧/跳帧/黑边/静音），同名视频可在「多版本对比」中横向比较。",
        ],
        "tips": [
            "Ctrl+F 搜索项目；↑/↓ 在列表间导航，Enter 打开；Ctrl+C/X/V 复制/剪切/粘贴，F2 重命名，Del 删除。",
            "双击左侧项目可同时展开其本地与服务器内容，便于对照。",
        ],
    },
    "local_only": {
        "import": [
            "打开「设置 → 项目」，在【本地项目根目录】处点击「添加」填入你本机的项目总目录（可添加多个）。",
            "本模式下无需配置任何服务器/NAS 目录，右侧「服务器匹配」栏将留空。",
            "添加后左侧项目导航会列出这些根目录下的项目，可直接展开浏览本地文件。",
        ],
        "manage": [
            "两栏可用：左=项目导航，中=本地内容；右侧服务器匹配栏在本模式下不参与。",
            "本地文件浏览：双击文件夹进入子目录，顶部「上级」按钮返回上层。",
            "文件操作：拖放复制/移动；右键菜单支持复制/剪切/粘贴/删除/重命名/新建/刷新。",
            "右键项目可重命名、删除；如需与服务器关联，随时到「设置」把模式切回「本地+服务器双索引」并填写服务器根目录。",
        ],
        "tips": [
            "Ctrl+F 搜索项目；↑/↓ 导航，Enter 打开；Ctrl+C/X/V 复制/剪切/粘贴，F2 重命名，Del 删除。",
            "想启用服务器同步：设置里切回「本地+服务器双索引」并补充服务器根目录即可，已有本地项目不会丢失。",
        ],
    },
    "server_only": {
        "import": [
            "打开「设置 → 项目」，在【服务器(NAS)根目录】处添加服务器/NAS 上的素材总目录（可多个，支持 \\\\server\\share 这类 UNC 路径）。",
            "本模式下只管理服务器上的项目素材，本地不做镜像，无需填写本地根目录。",
            "添加后软件会对该目录做索引，构建可搜索的项目列表。",
        ],
        "manage": [
            "两栏可用：左=项目导航，右=服务器内容；本地栏在本模式下不参与。",
            "服务器索引：目录添加后先快速扫描、再后台深度扫描；在「设置」开启「心跳自动刷新」定期拉取服务器最新内容。",
            "文件浏览：双击文件夹进入子目录，顶部「上级」返回上层；右键支持复制/剪切/粘贴/删除/重命名/新建/刷新。",
            "需要质检时：右键文件或文件夹直接发起 QC 检测；同名视频可在「多版本对比」中横向比较不同版本。",
        ],
        "tips": [
            "Ctrl+F 搜索项目；↑/↓ 导航，Enter 打开；Ctrl+C/X/V 复制/剪切/粘贴，F2 重命名，Del 删除。",
            "如本地已有同名素材想对照：到「设置」切回「本地+服务器双索引」并补充本地根目录即可。",
        ],
    },
}


def _build_guide_html(mode_key: str) -> str:
    g = GUIDANCE[mode_key]
    parts = ["<div style='line-height:1.8;'>"]
    parts.append(
        "<h3 style='color:%s; margin:16px 0 6px;'>📥 导入项目</h3>"
        "<ul style='margin:0; padding-left:20px;'>" % SECTION
    )
    for s in g["import"]:
        parts.append("<li style='margin:5px 0;'>%s</li>" % s)
    parts.append("</ul>")
    parts.append(
        "<h3 style='color:%s; margin:16px 0 6px;'>🗂️ 管理项目</h3>"
        "<ul style='margin:0; padding-left:20px;'>" % SECTION
    )
    for s in g["manage"]:
        parts.append("<li style='margin:5px 0;'>%s</li>" % s)
    parts.append("</ul>")
    if g.get("tips"):
        parts.append(
            "<h3 style='color:%s; margin:16px 0 6px;'>⌨️ 常用快捷键 & 提示</h3>"
            "<ul style='margin:0; padding-left:20px;'>" % SECTION
        )
        for s in g["tips"]:
            parts.append("<li style='margin:5px 0;'>%s</li>" % s)
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


class _ModeCard(QFrame):
    """可选中的卡片式单选。点击整张卡片即选中。"""

    clicked = Signal()

    def __init__(self, mode: dict, parent: QDialog | None = None):
        super().__init__(parent)
        self._mode = mode
        self.setObjectName("modeCard")  # 防止 QLabel(也是 QFrame) 继承 border 样式
        self._selected = False
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(92)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(14)

        self._check = QLabel("○")
        self._check.setFixedWidth(24)
        self._check.setAlignment(Qt.AlignCenter)
        self._check.setStyleSheet(f"font-size:18px; color:{CHECK_OFF};")

        body = QVBoxLayout()
        body.setSpacing(4)
        self._title = QLabel(
            f"<b style='font-size:14px;'>{self._mode['icon']} {self._mode['title']}</b>"
        )
        self._desc = QLabel(self._mode["desc"])
        self._desc.setWordWrap(True)
        self._desc.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        body.addWidget(self._title)
        body.addWidget(self._desc)

        root.addWidget(self._check)
        root.addLayout(body, 1)

    # ---- 状态切换 ----
    def set_selected(self, sel: bool):
        self._selected = sel
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            border, bg = ACCENT, ACCENT_SOFT
            self._check.setText("✓")
            self._check.setStyleSheet(f"font-size:18px; color:{ACCENT};")
        else:
            border = ACCENT if self._hovered else BORDER
            bg = "#F9FAFB" if self._hovered else "#FFFFFF"
            self._check.setText("○")
            self._check.setStyleSheet(f"font-size:18px; color:{CHECK_OFF};")
        self.setStyleSheet(
            f"#modeCard {{ border:2px solid {border}; border-radius:12px; "
            f"background:{bg}; }}"
        )

    # ---- 事件 ----
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_style()
        super().leaveEvent(event)


class _OnboardingDialog(QDialog):
    def __init__(self, parent: QDialog | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"欢迎使用 {APP_NAME}")
        self.setMinimumSize(600, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._cards: list[_ModeCard] = []
        self._selected_key = "both"

        self._stack = QStackedWidget()
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._stack)

        self._stack.addWidget(self._build_select_page())
        self._stack.addWidget(self._build_guide_page())
        self._select("both")  # 默认推荐项
        self._stack.setCurrentIndex(0)

    # ---------------- 第 1 步：选择方式 ----------------
    def _build_select_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(14)

        top = self._make_header("请选择适合你的工作方式", "之后可在「设置」中随时更改")
        v.addLayout(top)

        for m in MODES:
            card = _ModeCard(m, self)
            card.clicked.connect(lambda key=m["key"]: self._select(key))
            self._cards.append(card)
            v.addWidget(card)
        v.addStretch(1)

        next_btn = QPushButton("下一步")
        next_btn.setMinimumHeight(42)
        next_btn.setCursor(Qt.PointingHandCursor)
        next_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#FFFFFF; "
            "border-radius:8px; font-size:14px; font-weight:600; padding:0 28px; }"
            f"QPushButton:hover {{ background:#1D4ED8; }}"
        )
        next_btn.clicked.connect(self._go_guide)
        v.addWidget(next_btn, alignment=Qt.AlignRight)
        return page

    # ---------------- 第 2 步：使用指南 ----------------
    def _build_guide_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(12)

        self._guide_title = QLabel()
        self._guide_title.setStyleSheet("font-size:18px; font-weight:600; color:#111827;")
        self._guide_sub = QLabel("以下步骤帮你快速把项目用起来（都可在「设置」中调整）。")
        self._guide_sub.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        v.addWidget(self._guide_title)
        v.addWidget(self._guide_sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._guide_body = QLabel()
        self._guide_body.setWordWrap(True)
        self._guide_body.setTextFormat(Qt.RichText)
        self._guide_body.setStyleSheet("font-size:13px; color:#374151;")
        scroll.setWidget(self._guide_body)
        v.addWidget(scroll, 1)

        # 底部：上一步 / 开始使用
        bar = QHBoxLayout()
        bar.setSpacing(10)
        back_btn = QPushButton("上一步")
        back_btn.setMinimumHeight(42)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(
            "QPushButton { background:#F3F4F6; color:#374151; border-radius:8px; "
            "font-size:14px; padding:0 20px; }"
            "QPushButton:hover { background:#E5E7EB; }"
        )
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        start_btn = QPushButton("开始使用")
        start_btn.setMinimumHeight(42)
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#FFFFFF; "
            "border-radius:8px; font-size:14px; font-weight:600; padding:0 24px; }"
            f"QPushButton:hover {{ background:#1D4ED8; }}"
        )
        start_btn.clicked.connect(self._accept_choice)
        bar.addStretch(1)
        bar.addWidget(back_btn)
        bar.addWidget(start_btn)
        v.addLayout(bar)
        return page

    # ---------------- 公共 ----------------
    def _make_header(self, title: str, sub: str) -> QHBoxLayout:
        top = QHBoxLayout()
        logo_path = resource_path("assets/logo.png")
        if logo_path and os.path.isfile(logo_path):
            logo = QLabel()
            logo.setPixmap(
                QPixmap(logo_path).scaled(
                    48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            top.addWidget(logo)
        box = QVBoxLayout()
        box.addWidget(QLabel(f"<h2 style='margin:0;'>{APP_NAME}</h2>"))
        box.addWidget(QLabel(f"<span style='color:{MUTED}; font-size:12px;'>{sub}</span>"))
        top.addLayout(box)
        top.addStretch(1)
        return top

    def _select(self, key: str):
        self._selected_key = key
        for c in self._cards:
            c.set_selected(c._mode["key"] == key)

    def _go_guide(self):
        mode = next(m for m in MODES if m["key"] == self._selected_key)
        self._guide_title.setText(f"使用指南 · {mode['icon']} {mode['title']}")
        self._guide_body.setText(_build_guide_html(self._selected_key))
        self._guide_body.adjustSize()
        self._stack.setCurrentIndex(1)

    def _accept_choice(self):
        config_manager.project_mode = self._selected_key
        config_manager.onboarding_done = True
        self.accept()

    def keyPressEvent(self, event):
        if self._stack.currentIndex() == 0 and event.key() in (
            Qt.Key_1,
            Qt.Key_2,
            Qt.Key_3,
        ):
            self._select(MODES[event.key() - Qt.Key_1]["key"])
        else:
            super().keyPressEvent(event)

    def reject(self):
        # 关闭 / Esc 也按当前选择落盘，保证 project_mode 始终有意义
        self._accept_choice()


def run_onboarding() -> str:
    """若已引导过，直接返回当前模式；否则弹出引导框并写回配置。"""
    if config_manager.onboarding_done:
        return config_manager.project_mode
    dlg = _OnboardingDialog()
    dlg.exec()
    return config_manager.project_mode
