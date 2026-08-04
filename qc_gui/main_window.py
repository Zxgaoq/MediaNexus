"""
VideoQC Pro 主窗口
提供完整的视频质检 GUI 界面。

界面构建已拆分为 gui/widgets/ 下的独立 Widget 类（FilePanel / ResultPanel /
DetailPanel / Toolbar / BottomBar / StatusBar），本类只负责装配 Widget、
编排信号/槽以及所有业务处理逻辑，以保证重构前后行为一致。
"""

import os
import sys
import traceback
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidgetItem, QSplitter,
    QFileDialog, QMessageBox, QTreeWidgetItem,
    QHeaderView, QApplication, QTableWidgetItem,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QPixmap

from core.engine import DetectionEngine
from utils.config import ConfigManager
from utils.exporter import ExcelExporter
from utils.storage_manager import StorageManager
from qc_gui.multi_version_compare_dialog import MultiVersionCompareDialog
from qc_gui.styles import (
    GLOBAL_STYLESHEET, COLORS, get_status_style,
    generate_panel_icons,
)
from qc_gui.theme import theme_manager
from qc_gui.widgets import (
    FilePanel, ResultPanel, DetailPanel, Toolbar, BottomBar, StatusBar
)

# 支持的视频格式
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
    ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
    ".m2ts", ".mts", ".vob", ".ogv", ".rmvb", ".divx",
}


class DetectionThread(QThread):
    """检测线程 — QThread 子类，run() 在新线程中执行，信号自动 QueuedConnection 到主线程"""

    progress_updated = Signal(int, str)
    log_appended = Signal(str)
    detection_finished = Signal(list)

    def __init__(self, file_list, thread_count, parent=None):
        super().__init__(parent)
        self._file_list = list(file_list)
        self._thread_count = thread_count
        self._engine = None   # 保存引擎引用供 cancel 使用

    def run(self):
        """在子线程中执行（由 QThread 内部调度，不经过主线程事件循环）"""
        try:
            self.log_appended.emit(f"开始批量检测: {len(self._file_list)} 个文件, 线程数: {self._thread_count}")

            self._engine = DetectionEngine()
            self._engine.set_progress_callback(lambda p, m: self.progress_updated.emit(p, m))
            self._engine.set_log_callback(lambda m: self.log_appended.emit(m))

            results = self._engine.analyze_batch(
                self._file_list,
                max_workers=self._thread_count,
            )

            if not isinstance(results, list):
                results = list(results) if results else []

            self.log_appended.emit(f"检测线程完成，结果数: {len(results)}")
            self.detection_finished.emit(results)

        except Exception as e:
            self.log_appended.emit(f"检测线程异常: {e}")
            self.log_appended.emit(traceback.format_exc())
            self.detection_finished.emit([])

    def cancel(self):
        """请求取消当前检测（安全，不强制 kill 线程）"""
        if self._engine is not None:
            self._engine.cancel()


class ExpandStrip(QWidget):
    """折叠态文件面板的展开按钮：文件图标 + "展开" 文字竖条。

    继承 QWidget 而不是 QPushButton，以便在窄竖条内垂直堆叠图标和文字。
    hover 样式由程序化 setStyleSheet 控制（QSS :hover 对 QWidget 动态属性不可靠）。
    """
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("cssClass", "expand-strip")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("展开文件面板")
        self.setFixedSize(48, 72)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(28, 28)
        self._icon_label.setScaledContents(True)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        self._text_label = QLabel("展开")
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._text_label)

        self._normal_pixmap = None
        self._hover_pixmap = None
        self._hover_qss = ""
        # 非hover态由父级 QSS 控制，不需要本地 normal_qss

    def set_icons(self, normal: QPixmap, hover: QPixmap, palette: dict = None):
        self._normal_pixmap = normal
        self._hover_pixmap = hover
        self._icon_label.setPixmap(normal)
        if palette:
            accent = palette.get("accent", "#1A73E8")
            accent_hover = palette.get("accent_hover", "#1557B0")
            accent_light = palette.get("accent_light", "#E8F0FE")
            # hover 风格：浅蓝底 + 深蓝边框，图标保持 accent 色（不交换）
            self._hover_qss = (
                f'QWidget[cssClass="expand-strip"] {{ '
                f'background-color: {accent_light}; '
                f'border: 2px solid {accent}; '
                f'border-radius: 10px; '
                f'padding: 4px; '
                f'}}'
                f'QWidget[cssClass="expand-strip"] QLabel {{ '
                f'color: {accent_hover}; '
                f'background-color: transparent; '
                f'font-size: 10px; '
                f'font-weight: 600; '
                f'padding: 0px; '
                f'}}'
            )

    def enterEvent(self, event):
        """鼠标进入：应用柔和 hover 样式（浅蓝底 + 深蓝边框/文字，图标不变）"""
        if self._hover_qss:
            self.setStyleSheet(self._hover_qss)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开：清除本地样式表，恢复由父级 QSS 控制的外观"""
        self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.storage = StorageManager()
        self.engine = DetectionEngine()  # 用于环境检查等非线程操作
        self.exporter = ExcelExporter()
        self._file_list = []
        self._results = []
        self._is_running = False
        self._detection_thread = None
        self._tm = theme_manager()

        # 迁移旧版散落文件
        self.storage.migrate_legacy_files()

        self._init_ui()
        self._init_theme()
        self._restore_geometry()
        self._check_environment()

    def showEvent(self, event):
        """窗口显示时兜底确保不低于最小尺寸（防止多屏/DPI 下最小尺寸被绕过）"""
        super().showEvent(event)
        min_size = self.minimumSizeHint()
        cur = self.size()
        if cur.width() < min_size.width() or cur.height() < min_size.height():
            self.resize(max(cur.width(), min_size.width()),
                        max(cur.height(), min_size.height()))

    def _init_ui(self):
        """初始化界面（装配各 Widget，信号在 MainWindow 统一编排）"""
        self.setWindowTitle("影枢 QC")
        self.setMinimumSize(1100, 700)
        self.resize(1200, 750)

        # 设置窗口图标 —— 与主程序一致的透明版 Logo
        import sys as _sys
        _root = getattr(_sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_path = os.path.join(_root, "assets", "logo.png")
        if os.path.isfile(icon_path):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))

        # 应用全局样式
        self.setStyleSheet(GLOBAL_STYLESHEET)

        # 启用拖放
        self.setAcceptDrops(True)

        # 中心组件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # === 顶部工具栏 ===
        self.toolbar = Toolbar()
        main_layout.addWidget(self.toolbar)
        self.toolbar.btn_multi_version_compare.clicked.connect(self._open_multi_version_compare)

        # === 主内容区域 ===
        # 使用 QHBoxLayout 包裹：展开按钮 + Splitter
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # ── 文件面板展开按钮（折叠态时可见，文件图标 + "展开" 文字竖条） ──
        self._panel_icons = generate_panel_icons(COLORS)
        self._expand_btn = ExpandStrip()
        self._expand_btn.set_icons(
            QPixmap(self._panel_icons["folder"]),
            QPixmap(self._panel_icons["folder-hover"]),
            palette=COLORS,
        )
        self._expand_btn.setVisible(False)  # 初始隐藏（文件面板展开态）
        self._expand_btn.clicked.connect(self._expand_file_panel)
        content_layout.addWidget(self._expand_btn)

        # ── Splitter: [文件面板 | 结果面板 | 详情面板] ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- 左侧面板：文件列表 --
        self.file_panel = FilePanel()
        self.splitter.addWidget(self.file_panel)
        self.drop_area = self.file_panel.drop_area
        self.file_list_widget = self.file_panel.file_list_widget
        self.file_count_label = self.file_panel.file_count_label
        self.file_panel.btn_add_files.clicked.connect(self._add_files)
        self.file_panel.btn_add_folder.clicked.connect(self._add_folder)
        self.file_panel.btn_clear.clicked.connect(self._clear_files)
        self.file_panel.panel_collapsed.connect(self._on_file_panel_collapsed)
        self.file_panel.panel_expanded.connect(self._on_file_panel_expanded)

        # -- 中间面板：结果预览 --
        self.result_panel = ResultPanel()
        self.splitter.addWidget(self.result_panel)
        self.result_tree = self.result_panel.result_tree
        self.result_tree.itemClicked.connect(self._on_result_clicked)
        self.result_tree.itemExpanded.connect(self._on_item_expanded)
        self._current_expanded_item = None

        # -- 右侧面板：详情与日志 --
        self.detail_panel = DetailPanel()
        self.splitter.addWidget(self.detail_panel)
        self.detail_tabs = self.detail_panel.detail_tabs
        self.metadata_tab = self.detail_panel.metadata_tab
        self.consistency_tab = self.detail_panel.consistency_tab
        self.anomaly_tab = self.detail_panel.anomaly_tab
        self.log_tab = self.detail_panel.log_tab

        # 允许文件面板折叠到 0
        self.splitter.setCollapsible(0, True)
        self.splitter.setSizes([320, 500, 380])
        content_layout.addWidget(self.splitter, 1)

        main_layout.addLayout(content_layout, 1)

        # === 底部控制栏 ===
        self.bottom_bar = BottomBar(
            default_threads=self.config.performance.get("max_threads", 4)
        )
        main_layout.addWidget(self.bottom_bar)
        self.progress_bar = self.bottom_bar.progress_bar
        self.thread_spin = self.bottom_bar.thread_spin
        self.btn_start = self.bottom_bar.btn_start
        self.btn_cancel = self.bottom_bar.btn_cancel
        self.btn_export = self.bottom_bar.btn_export
        self.btn_start.clicked.connect(self._start_detection)
        self.btn_cancel.clicked.connect(self._cancel_detection)
        self.btn_export.clicked.connect(self._export_excel)

        # === 状态栏 ===
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = self.status_bar.status_label

        # === 菜单栏 ===
        self._create_menu_bar()

    def _init_theme(self):
        """初始化主题系统：从配置读取、应用样式、连接切换信号"""
        # 从配置加载主题
        saved_theme = self.config.theme
        self._tm.set_theme(saved_theme)

        # 应用主题样式表
        self._apply_theme()

        # 连接主题切换按钮
        self.toolbar.update_theme_button(self._tm.theme)
        self.toolbar.btn_theme_toggle.clicked.connect(self._on_theme_toggle)

        # 连接 ThemeManager 信号 → 主题变化时重新应用样式
        self._tm.theme_changed.connect(self._on_theme_changed)

    def _apply_theme(self):
        """应用当前主题的完整样式表到整个应用"""
        qss = self._tm.get_stylesheet()
        self.setStyleSheet(qss)
        # 更新拖放区样式（使用新调色板）— 仅在展开态需要
        if not self.file_panel.is_collapsed:
            from qc_gui.styles import get_drop_area_stylesheet
            self.file_panel.drop_area.setStyleSheet(get_drop_area_stylesheet("normal"))
        # 更新面板图标（主题切换时颜色自动适配）
        self._panel_icons = generate_panel_icons(self._tm.palette)
        self._expand_btn.set_icons(
            QPixmap(self._panel_icons["folder"]),
            QPixmap(self._panel_icons["folder-hover"]),
            palette=self._tm.palette,
        )
        self.file_panel._panel_icons = self._panel_icons
        self.file_panel._collapse_btn.setIcon(QIcon(self._panel_icons["collapse"]))

    # ── 文件面板折叠 / 展开 ──

    def _collapse_file_panel(self):
        """折叠文件面板：Splitter 尺寸变为 [0, ~50%, ~50%]"""
        if self.file_panel.is_collapsed:
            return
        self.file_panel.collapse()
        # Splitter 自动调整：文件面板 0 → 结果/详情均分空间

    def _expand_file_panel(self):
        """展开文件面板：恢复 Splitter 尺寸"""
        if not self.file_panel.is_collapsed:
            return
        self.file_panel.expand()
        # Splitter 自动调整：恢复 [320, 500, 380]

    def _on_file_panel_collapsed(self):
        """文件面板折叠后的 UI 更新"""
        # 将剩余空间均分给结果面板和详情面板
        total = self.splitter.width()
        half = total // 2
        self.splitter.setSizes([0, half, total - half])
        # 显示展开按钮
        self._expand_btn.setVisible(True)

    def _on_file_panel_expanded(self):
        """文件面板展开后的 UI 更新"""
        # 恢复原始比例
        total = self.splitter.width()
        fp_width = min(320, total // 4)
        remain = total - fp_width
        result_width = int(remain * 500 / 880)
        detail_width = remain - result_width
        self.splitter.setSizes([fp_width, result_width, detail_width])
        # 隐藏展开按钮
        self._expand_btn.setVisible(False)
        # 恢复拖放区样式
        from qc_gui.styles import get_drop_area_stylesheet
        self.file_panel.drop_area.setStyleSheet(get_drop_area_stylesheet("normal"))

    def _on_theme_toggle(self):
        """点击主题切换按钮"""
        self._tm.toggle()

    def _on_theme_changed(self, theme_name):
        """主题变化时重新应用样式并持久化"""
        self._apply_theme()
        self.toolbar.update_theme_button(theme_name)
        # 保存到配置
        self.config.theme = theme_name

    def _restore_geometry(self):
        """恢复上次保存的窗口几何"""
        geo = self.config.get("window_geometry", "")
        if geo:
            from PySide6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromHex(geo.encode()))

    def _save_geometry(self):
        """保存当前窗口几何到配置"""
        geo = self.saveGeometry().toHex().data().decode()
        self.config.set("window_geometry", geo)

    # ========== 菜单栏 ==========
    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        # 文件菜单
        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction("添加文件(&A)", "Ctrl+O", self._add_files)
        file_menu.addAction("添加文件夹(&D)", "Ctrl+Shift+O", self._add_folder)
        file_menu.addSeparator()
        file_menu.addAction("导出 Excel(&E)", "Ctrl+E", self._export_excel)
        file_menu.addSeparator()
        file_menu.addAction("退出(&X)", "Alt+F4", self.close)

        # 工具菜单
        tools_menu = menu_bar.addMenu("工具(&T)")
        tools_menu.addAction("环境检查(&V)", "Ctrl+Shift+V", self._check_environment)

        # 帮助菜单（使用手册统一由主程序「帮助」菜单提供，避免重复）
        help_menu = menu_bar.addMenu("帮助(&H)")
        help_menu.addAction("关于(&A)", self._show_about)

    # ========== 拖放支持 ==========
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.file_panel.set_drop_state("hover")

    def dragLeaveEvent(self, event):
        self.file_panel.set_drop_state("normal")

    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                self._scan_folder(p, paths)
            elif os.path.isfile(p):
                paths.append(p)

        self._add_paths(paths)
        self.file_panel.set_drop_state("normal")

    # ========== 文件操作 ==========
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v *.mpg *.mpeg *.ts *.3gp);;所有文件 (*.*)"
        )
        if files:
            self._add_paths(files)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            paths = []
            self._scan_folder(folder, paths)
            self._add_paths(paths)

    def _scan_folder(self, folder, paths):
        """递归扫描文件夹中的视频文件"""
        try:
            for entry in os.scandir(folder):
                if entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        paths.append(entry.path)
                elif entry.is_dir():
                    self._scan_folder(entry.path, paths)
        except PermissionError:
            pass

    def _add_paths(self, paths):
        """添加路径到文件列表（去重）"""
        existing = set(self._file_list)
        added = 0
        for p in paths:
            p = os.path.normpath(p)
            if p not in existing and os.path.isfile(p):
                existing.add(p)
                self._file_list.append(p)

                # UI 项
                item = QListWidgetItem(os.path.basename(p))
                item.setToolTip(p)
                self.file_list_widget.addItem(item)
                added += 1

        self.file_count_label.setText(f"共 {len(self._file_list)} 个文件")
        self.status_label.setText(f"已添加 {added} 个文件")

    def _clear_files(self):
        self._file_list.clear()
        self._results.clear()
        self.file_list_widget.clear()
        self.result_tree.clear()
        self.metadata_tab.clear()
        self.anomaly_tab.clear()
        self.file_count_label.setText("共 0 个文件")
        self.status_label.setText("列表已清空")

    # ========== 检测控制 ==========
    def _start_detection(self):
        if not self._file_list:
            QMessageBox.warning(self, "提示", "请先添加视频文件")
            return

        if self._is_running:
            return

        self._is_running = True
        self._results = []
        self.result_tree.clear()
        self.progress_bar.setValue(0)

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_export.setEnabled(False)

        # 保存线程设置（持久化到磁盘，重启不丢失）
        self.config.set("performance.max_threads", self.thread_spin.value(), persist=True)

        # ── 安全清理上一个线程 ──
        old_thread = self._detection_thread
        if old_thread is not None:
            # 断开旧线程的所有信号（防止残留信号污染新线程）
            try:
                old_thread.progress_updated.disconnect()
                old_thread.log_appended.disconnect()
                old_thread.detection_finished.disconnect()
                old_thread.finished.disconnect()
            except TypeError:
                pass  # 信号可能已经断开
            # 请求旧线程取消
            if old_thread.isRunning():
                old_thread.cancel()
            # 让旧线程的 finished 信号自动触发 self._cleanup_old_thread
            old_thread.finished.connect(lambda t=old_thread: self._cleanup_old_thread(t))
            self._detection_thread = None

        # 创建检测线程
        thread_count = self.thread_spin.value()
        self._detection_thread = DetectionThread(
            self._file_list, thread_count, parent=self
        )

        # 连接信号（DetectionThread 对象在主线程，emit 从子线程 → 自动 QueuedConnection）
        self._detection_thread.progress_updated.connect(self._on_progress_ui)
        self._detection_thread.log_appended.connect(self._on_log_ui)
        self._detection_thread.detection_finished.connect(self._on_detection_finished)
        # 用 sender() 确保只清理真正完成的那个线程
        self._detection_thread.finished.connect(lambda: self._on_thread_finished(self._detection_thread))

        self._detection_thread.start()

        # 检测启动后自动折叠文件面板，释放空间给结果/详情
        self._collapse_file_panel()

    def _cleanup_old_thread(self, thread):
        """清理已完成的旧线程（通过 sender 方式避免误删新线程）"""
        if thread is not None:
            thread.deleteLater()

    def _on_thread_finished(self, thread):
        """QThread.finished 信号 — 只清理参数指定的线程对象"""
        if thread is not None and thread is self._detection_thread:
            # 只有当前活跃线程完成时才清理
            self._detection_thread = None
            thread.deleteLater()

    def _cancel_detection(self):
        """安全取消：通过引擎 cancel_flag 协作停止，不强制杀线程"""
        if self._detection_thread and self._detection_thread.isRunning():
            self._detection_thread.cancel()

    def _on_progress_ui(self, percent, message):
        """更新进度条（主线程，由 worker 信号触发）"""
        self.progress_bar.setValue(percent)
        if message:
            self.status_label.setText(message)

    def _on_log_ui(self, message):
        """更新日志面板（主线程，由 worker 信号触发）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_tab.appendPlainText(f"[{timestamp}] {message}")

    def _on_detection_finished(self, results):
        """检测完成后更新 UI（主线程，由 detection_finished 信号触发）"""
        self._is_running = False
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_export.setEnabled(True)

        # 安全处理结果
        if results is None:
            results = []
        if not isinstance(results, list):
            results = list(results)

        self._results = results

        self._update_result_tree()

        # 统计
        pass_count = sum(1 for r in self._results if r and r.get("overall_status") == "pass")
        warn_count = sum(1 for r in self._results if r and r.get("overall_status") == "warning")
        fail_count = sum(1 for r in self._results if r and r.get("overall_status") in ("fail", "error"))

        self.status_label.setText(
            f"检测完成: 🟢{pass_count} 通过 | 🟡{warn_count} 警告 | 🔴{fail_count} 不合格"
        )
        self.progress_bar.setValue(100)

        self._on_log_ui(f"✅ 检测完成: 共 {len(self._results)} 个文件")
        # 播放提示音 + 任务栏通知
        self._do_play_notification()
        self._do_taskbar_notification()

    @staticmethod
    def _do_play_notification():
        """播放检测完成提示音：
        1. 如果 resources/sounds/notification.wav 存在，播放自定义音效
        2. 否则播放系统提示音（SND_NODE 确保不阻塞 UI）
        """
        try:
            # 查找自定义通知音效文件
            project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            custom_sound = os.path.join(project_dir, "resources", "sounds", "notification.wav")

            if sys.platform == "win32":
                import winsound
                if os.path.isfile(custom_sound):
                    # 播放自定义 WAV 文件（异步，不阻塞UI）
                    winsound.PlaySound(custom_sound, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    # 使用系统提示音（异步）
                    winsound.MessageBeep(winsound.MB_ICONINFORMATION)
            else:
                # macOS / Linux：尝试播放自定义文件，否则系统 beep
                if os.path.isfile(custom_sound):
                    # 尝试使用系统命令播放
                    import subprocess
                    subprocess.Popen(["afplay", custom_sound],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    QApplication.beep()
        except Exception:
            # fallback: 使用 QApplication.beep()
            try:
                QApplication.beep()
            except Exception:
                pass

    def _do_taskbar_notification(self):
        """检测完成后在任务栏闪烁窗口图标，提醒用户查看结果"""
        try:
            # 如果窗口不是焦点窗口，闪烁任务栏图标
            if not self.isActiveWindow():
                if sys.platform == "win32":
                    import ctypes
                    # Windows 任务栏闪烁（FLASHW_ALL = 标题栏 + 任务栏）
                    hwnd = int(self.winId())
                    from ctypes import wintypes
                    user32 = ctypes.windll.user32

                    class FLASHWINFO(ctypes.Structure):
                        _fields_ = [
                            ("cbSize", wintypes.UINT),
                            ("hwnd", wintypes.HWND),
                            ("dwFlags", wintypes.UINT),
                            ("uCount", wintypes.UINT),
                            ("dwTimeout", wintypes.DWORD),
                        ]

                    FLASHW_ALL = 0x00000003  # 标题栏 + 任务栏闪烁
                    FLASHW_TIMERNOFG = 0x0000000C  # 闪烁直到窗口获得焦点

                    fi = FLASHWINFO()
                    fi.cbSize = ctypes.sizeof(FLASHWINFO)
                    fi.hwnd = hwnd
                    fi.dwFlags = FLASHW_ALL | FLASHW_TIMERNOFG
                    fi.uCount = 5  # 闪烁次数
                    fi.dwTimeout = 0  # 默认闪烁频率

                    user32.FlashWindowEx(fi)
                # 通用方式：弹起窗口到前台
                self.raise_()
        except Exception:
            pass

    def _update_result_tree(self):
        """更新结果树"""
        self.result_tree.clear()

        # 检测是否有全局一致性数据
        has_consistency = any(r and r.get("_consistency_matrix") for r in self._results)

        for result in self._results:
            if not result or not isinstance(result, dict):
                continue
            meta = result.get("metadata") or {}
            meta.get("video") or {}
            meta.get("audio") or {}
            status = result.get("overall_status", "pending")

            # 检测项目状态
            bf = result.get("black_frame") or {}
            ff = result.get("flash_frame") or {}
            bb = result.get("black_border") or {}
            sd = result.get("silence") or {}
            cons = result.get("consistency") or {}

            def check_mark(has_issue):
                return "✗" if has_issue else "✓"

            # 直接传异常状态（有异常=✗，无异常=✓）
            bf_has = bf.get("has_black_frames", False)
            ff_has = ff.get("has_flash_frames", False)
            bb_has = bb.get("has_black_border", False)
            sd_has = sd.get("has_silence", False)

            # 一致性状态
            if has_consistency:
                if cons.get("is_baseline"):
                    cons_text = "基准"
                elif cons.get("is_consistent", True):
                    cons_text = "✓"
                else:
                    cons_text = f"✗ ({len(cons.get('inconsistencies', []))})"
            else:
                cons_text = "-"

            item = QTreeWidgetItem([
                result.get("filename", "未知"),
                get_status_style(status)["icon"],
                cons_text,
                check_mark(bf_has),
                check_mark(ff_has),
                check_mark(bb_has),
                check_mark(sd_has),
            ])

            item.setData(0, Qt.ItemDataRole.UserRole, self.result_tree.topLevelItemCount())

            # 根据状态着色
            get_status_style(status)
            for col in range(7):
                item.setBackground(col, Qt.GlobalColor.transparent)

            # 一致性不通过的整行高亮
            if not cons.get("is_consistent", True) and not cons.get("is_baseline"):
                from PySide6.QtGui import QColor
                item.setBackground(0, QColor(COLORS["warning_bg"]))

            self.result_tree.addTopLevelItem(item)

            # 子项：详细信息
            if meta:
                vid = meta.get("video") or {}
                aud = meta.get("audio") or {}
                info_item = QTreeWidgetItem([
                    "📋 元数据",
                    f"{vid.get('codec', '?')} • {vid.get('resolution', '?')} • {vid.get('fps', '?')}fps",
                    "", "", "", "", ""
                ])
                item.addChild(info_item)

                ch_str = aud.get('channels_str') or f"{aud.get('channels', '?')}ch"
                audio_item = QTreeWidgetItem([
                    "🎵 音频",
                    f"{aud.get('codec', '?')} • {aud.get('sample_rate_str', aud.get('sample_rate', '?'))} • {ch_str}",
                    "", "", "", "", ""
                ])
                item.addChild(audio_item)

            # 异常子项
            bf_segs = bf.get("segments", [])
            if bf_segs:
                for seg in bf_segs[:3]:
                    fc = seg.get('frame_count', 0)
                    anomaly_item = QTreeWidgetItem([
                        "⬛ 黑帧",
                        f"{seg.get('start_time', 0):.1f}s ~ {seg.get('end_time', 0):.1f}s ({fc}帧)",
                        seg.get("severity", ""),
                        "", "", "", ""
                    ])
                    item.addChild(anomaly_item)

            ff_cands = ff.get("candidates", [])
            if ff_cands:
                for cand in ff_cands[:3]:
                    cand_type = cand.get("type", "夹帧")
                    span = cand.get("span_frames", 1)
                    dur = cand.get("duration_ms", 0)
                    conf = cand.get("confidence", "?")
                    level = cand.get("confidence_level", "")
                    anomaly_item = QTreeWidgetItem([
                        f"⚡ {cand_type}",
                        f"帧 {cand.get('start_frame', '?')}~{cand.get('end_frame', '?')} ({span}帧/{dur:.0f}ms)",
                        f"{level} {conf}%",
                        f"恢复={cand.get('recovery_score', '?')}",
                        f"异常分={cand.get('anomaly_score', '?')}",
                        "",
                        ""
                    ])
                    item.addChild(anomaly_item)

            sd_segs = sd.get("segments", [])
            if sd_segs:
                for seg in sd_segs[:3]:
                    anomaly_item = QTreeWidgetItem([
                        "🔇 静音",
                        f"{seg.get('start', 0):.1f}s - {seg.get('end', 0):.1f}s",
                        seg.get("severity", ""),
                        "", "", "", ""
                    ])
                    item.addChild(anomaly_item)

            # 黑边时间段子项
            bb_segs = bb.get("segments", [])
            if bb_segs:
                for seg in bb_segs[:5]:
                    border_desc = seg.get("border_type", "")
                    anomaly_item = QTreeWidgetItem([
                        "🖼 黑边",
                        f"{seg.get('start_time', 0):.1f}s - {seg.get('end_time', 0):.1f}s ({seg.get('duration', 0):.1f}s) {border_desc}",
                        seg.get("severity", ""),
                        "", "", "", ""
                    ])
                    item.addChild(anomaly_item)

            # 不一致子项
            for inc in cons.get("inconsistencies", [])[:3]:
                inc_item = QTreeWidgetItem([
                    "📐 不一致",
                    f"{inc['param']}: {inc['expected']} → {inc['actual']}",
                    inc.get("severity", ""),
                    "", "", "", ""
                ])
                item.addChild(inc_item)

    def _on_item_expanded(self, item):
        """单展开模式：展开新项时收起上一个"""
        if self._current_expanded_item and self._current_expanded_item is not item:
            self._current_expanded_item.setExpanded(False)
        self._current_expanded_item = item

    def _on_result_clicked(self, item, column):
        """点击结果项时显示详细信息"""
        # 查找顶级项
        while item.parent():
            item = item.parent()

        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is None or index >= len(self._results):
            return

        result = self._results[index]
        if result is None:
            return
        self._show_metadata(result)
        self._show_consistency(result)
        self._show_anomalies(result)

    def _show_metadata(self, result):
        """显示元数据（增强版）"""
        self.metadata_tab.clear()

        meta = result.get("metadata")
        if not meta:
            return

        # ── 文件信息 ──
        file_root = QTreeWidgetItem(["📁 文件信息", ""])
        self.metadata_tab.addTopLevelItem(file_root)
        file_root.addChild(QTreeWidgetItem(["文件名", meta.get("filename", "未知")]))
        file_root.addChild(QTreeWidgetItem(["文件大小", f"{meta.get('filesize_mb', 0)} MB"]))
        file_root.addChild(QTreeWidgetItem(["封装格式", meta.get("format_name", "未知")]))
        file_root.addChild(QTreeWidgetItem(["总码率", meta.get("overall_bitrate_str", "未知")]))
        dur = meta.get("duration")
        dur_str = meta.get("duration_hms") or (f"{dur:.1f} 秒" if dur else "未知")
        file_root.addChild(QTreeWidgetItem(["时长", dur_str]))

        # ── 视频流 ──
        video = meta.get("video")
        if video:
            vid_root = QTreeWidgetItem(["🎬 视频流", ""])
            self.metadata_tab.addTopLevelItem(vid_root)
            fields = [
                ("codec_long", "编码格式"),
                ("codec_tag", "FourCC"),
                ("profile", "编码档次"),
                ("level", "Level"),
                ("resolution", "分辨率"),
                ("display_aspect_ratio", "画面比例 (DAR)"),
                ("fps", "帧率"),
                ("fps_exact", "精确帧率"),
                ("bitrate_str", "码率"),
                ("pix_fmt", "像素格式"),
                ("bits_per_sample", "位深 (bits)"),
                ("color_space", "色彩空间"),
                ("color_transfer", "传输函数"),
                ("color_primaries", "色彩原色"),
                ("color_range", "色彩范围"),
                ("is_hdr", "HDR"),
                ("rotation", "旋转角度"),
            ]
            for key, label in fields:
                val = video.get(key)
                if val is not None and val != "":
                    if key == "is_hdr":
                        val = "是" if val else "否"
                    if key == "rotation" and val == 0:
                        continue  # 无旋转时不显示
                    vid_root.addChild(QTreeWidgetItem([label, str(val)]))

        # ── 音频流 ──
        audio = meta.get("audio")
        if audio:
            aud_root = QTreeWidgetItem(["🎵 音频流", ""])
            self.metadata_tab.addTopLevelItem(aud_root)
            fields = [
                ("codec_long", "编码格式"),
                ("codec_tag", "FourCC"),
                ("sample_rate_str", "采样率"),
                ("channels_str", "声道数"),
                ("channel_layout", "声道布局"),
                ("bits_per_sample", "位深度 (bits)"),
                ("bitrate_str", "码率"),
                ("sample_fmt", "采样格式"),
                ("language", "语言"),
            ]
            for key, label in fields:
                val = audio.get(key)
                if val is not None and val != "":
                    aud_root.addChild(QTreeWidgetItem([label, str(val)]))

        self.metadata_tab.expandAll()

    def _show_anomalies(self, result):
        """显示异常详情"""
        text = []
        text.append(f"## 文件: {result.get('filename', '')}\n")

        # 黑帧
        bf = result.get("black_frame") or {}
        if bf.get("segments"):
            text.append("### ⬛ 黑帧检测")
            for seg in bf["segments"]:
                fc = seg.get('frame_count', 0)
                text.append(f"- {seg['start_time']:.1f}s ~ {seg['end_time']:.1f}s "
                           f"({fc}帧) [{seg['severity']}]")
        else:
            text.append("### ⬛ 黑帧检测: ✓ 未发现\n")

        # 夹帧/跳帧
        ff = result.get("flash_frame") or {}
        if ff.get("candidates"):
            text.append("### ⚡ 夹帧/跳帧检测")
            for cand in ff["candidates"]:
                cand_type = cand.get("type", "夹帧")
                span = cand.get("span_frames", 1)
                time_str = cand.get("time_str", "")
                line = (f"- 帧 {cand.get('start_frame', '?')}~{cand.get('end_frame', '?')} "
                        f"({span}帧) {time_str} "
                        f"[{cand_type}]")
                text.append(line)
        else:
            text.append("### ⚡ 夹帧/跳帧检测: ✓ 未发现\n")

        # 黑边
        bb = result.get("black_border") or {}
        text.append("### 🖼 黑边检测")
        text.append(f"- 扫描帧数: {bb.get('frames_checked', 0)} (总帧数: {bb.get('total_frames', '?')})")
        text.append(f"- 分辨率: {bb.get('resolution', '?')}")
        bb_segs = bb.get("segments", [])
        if bb_segs:
            text.append(f"- **发现 {len(bb_segs)} 个黑边时间段:**\n")
            for seg in bb_segs:
                text.append(f"  - **{seg['start_time']:.1f}s ~ {seg['end_time']:.1f}s** "
                           f"(持续 {seg['duration']:.1f}s) [{seg['severity']}] "
                           f"位置: {seg.get('border_type', '?')}")
                text.append(f"    - 平均: 上{seg.get('avg_top_px',0)}px 下{seg.get('avg_bottom_px',0)}px "
                           f"左{seg.get('avg_left_px',0)}px 右{seg.get('avg_right_px',0)}px")
                text.append(f"    - 最大: 上{seg.get('max_top_px',0)}px 下{seg.get('max_bottom_px',0)}px "
                           f"左{seg.get('max_left_px',0)}px 右{seg.get('max_right_px',0)}px")
        else:
            text.append("- ✓ 未发现黑边")
        if bb.get("max_border_px"):
            mb = bb["max_border_px"]
            text.append(f"- 全局最大黑边: 上{mb.get('top',0)}px 下{mb.get('bottom',0)}px "
                       f"左{mb.get('left',0)}px 右{mb.get('right',0)}px")

        # 静音
        sd = result.get("silence") or {}
        if sd.get("no_audio"):
            text.append("\n### 🔇 静音检测: 无音频流，跳过")
        elif sd.get("segments"):
            text.append("\n### 🔇 静音检测")
            for seg in sd["segments"]:
                text.append(f"- {seg['start']:.1f}s ~ {seg['end']:.1f}s "
                           f"(持续 {seg['duration']:.1f}s) [{seg['severity']}]")
            text.append(f"- 总静音时长: {sd.get('total_silence_duration', 0):.1f}s")
        else:
            text.append("\n### 🔇 静音检测: ✓ 未发现异常静音")

        # 一致性
        cons = result.get("consistency") or {}
        if cons and cons.get("inconsistencies"):
            text.append("\n### 📐 一致性检查")
            for inc in cons["inconsistencies"]:
                text.append(f"- {inc['param']}: 基准={inc['expected']}, 实际={inc['actual']} [{inc['severity']}]")

        self.anomaly_tab.setMarkdown("\n".join(text))

    def _show_consistency(self, result):
        """在一致性对比标签页中显示全量参数对比表"""
        matrix = result.get("_consistency_matrix", {})
        if not matrix:
            self.consistency_tab.clear()
            self.consistency_tab.setRowCount(0)
            self.consistency_tab.setColumnCount(0)
            self.consistency_tab.setHorizontalHeaderLabels([])
            return

        # 收集所有文件名
        all_files = []
        for param_data in matrix.values():
            for fname in param_data.get("values", {}):
                if fname not in all_files:
                    all_files.append(fname)

        # 构建表格：行 = 参数，列 = 文件名
        params = list(matrix.items())
        self.consistency_tab.clear()
        self.consistency_tab.setRowCount(len(params))
        self.consistency_tab.setColumnCount(1 + len(all_files))
        self.consistency_tab.setHorizontalHeaderLabels(["检测参数"] + all_files)

        for row_idx, (param_key, param_data) in enumerate(params):
            label = param_data.get("label", param_key)
            values = param_data.get("values", {})

            # 参数名列
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.consistency_tab.setItem(row_idx, 0, label_item)

            # 检查该参数各文件值是否一致
            unique_vals = set(values.values())
            is_inconsistent = len(unique_vals) > 1

            for col_idx, fname in enumerate(all_files):
                val = values.get(fname, "—")
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if is_inconsistent and val != list(unique_vals)[0]:
                    from PySide6.QtGui import QColor
                    item.setBackground(QColor(COLORS["error_bg"]))  # 差异值高亮
                self.consistency_tab.setItem(row_idx, 1 + col_idx, item)

        self.consistency_tab.resizeColumnsToContents()
        self.consistency_tab.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

    # ========== 导出 ==========
    def _export_excel(self):
        if not self._results:
            QMessageBox.warning(self, "提示", "没有可导出的检测结果")
            return

        # 使用规范的导出目录作为默认位置
        default_dir = self.config.get("last_output_dir") or self.storage.exports_dir
        default_name = f"VideoQC_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        default_path = os.path.join(default_dir, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "导出质检报告", default_path,
            "Excel 文件 (*.xlsx)"
        )
        if not path:
            return

        try:
            self.exporter.export(self._results, {}, path)
            self.config.set("last_output_dir", os.path.dirname(path))
            QMessageBox.information(self, "导出成功", f"报表已导出到:\n{path}")
            self._on_log_ui(f"📥 报表已导出: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出过程出错:\n{e}")

    def _open_multi_version_compare(self):
        """打开多版本对比对话框"""
        dialog = MultiVersionCompareDialog(self)
        dialog.exec()

    # ========== 环境检查 ==========
    def _check_environment(self):
        """检查运行环境"""
        ok, msg = self.engine.validate_environment()
        self._on_log_ui("=== 环境检查 ===")
        for line in msg.split("\n"):
            self._on_log_ui(line)

        if not ok:
            QMessageBox.warning(
                self, "环境检查",
                "部分组件未就绪:\n\n" + msg + "\n\n"
                "请确保:\n"
                "1. FFmpeg 已放入 resources/ffmpeg/ 目录\n"
                "2. 已安装必要的 Python 包"
            )
        else:
            self.status_label.setText("✅ 环境就绪")

    # ========== 帮助 ==========
    def _show_about(self):
        QMessageBox.about(
            self, "关于 影枢 QC",
            "<h2>影枢 QC</h2>"
            "<p>视频批量质量检测工具（MediaNexus 一体化套件之质检子系统）</p>"
            "<p>功能: 视频元数据提取、黑帧/夹帧/跳帧/黑边/静音检测、一致性校验、多版本对比</p>"
            "<p>技术栈: Python + PySide6 + FFmpeg + OpenCV</p>"
        )

    # ========== 关闭事件 ==========
    def closeEvent(self, event):
        if self._is_running:
            reply = QMessageBox.question(
                self, "确认退出",
                "检测任务正在进行中，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            # 立即反馈 + 取消检测（协作退出，不强制 kill）
            self.status_label.setText("正在停止…")
            QApplication.processEvents()
            if self._detection_thread and self._detection_thread.isRunning():
                self._detection_thread.cancel()
                self._detection_thread.wait(2000)

        # 保存窗口几何
        self._save_geometry()
        event.accept()
