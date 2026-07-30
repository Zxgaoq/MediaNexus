# -*- coding: utf-8 -*-
"""
MediaNexus - 主窗口（三栏式布局 + 整体调度）

布局：左(项目导航) | 中(本地内容) | 右(服务器匹配)
负责：配置加载、NAS 索引调度（进度/暂停）、模糊匹配调度、
      快捷键（Ctrl+F / ↑↓ / Enter）、双击侧栏同时打开本地+NAS。
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..config_manager import config_manager
from .. import indexer as nas_indexer
from ..constants import APP_NAME, APP_VERSION, STYLESHEET
from ..utils import resource_path
from ..workers import DeepScanWorker, IndexWorker, MatchWorker, RefreshIndexWorker, make_flags
from ..watcher import NASWatcherManager
from ..worker_manager import WorkerManager
from .left_sidebar import LeftSidebar
from .middle_panel import MiddlePanel
from .right_panel import RightPanel
from .settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        self.resize(1280, 800)
        # 设置窗口图标（任务栏 / 标题栏）—— 透明版 Logo
        logo_path = resource_path("assets/logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self._nas_folders: list[str] = []
        self._current_project: dict | None = None
        self._index_worker: IndexWorker | None = None
        self._match_worker: MatchWorker | None = None
        self._refresh_worker: RefreshIndexWorker | None = None
        self._deep_scan_worker: DeepScanWorker | None = None
        self._pause_event, self._stop_event = make_flags()
        self._wm = WorkerManager()  # Worker 统一管理器
        self._watcher = NASWatcherManager()  # 实时监控 NAS 目录变更
        self._watcher.on_changed = self._on_watcher_changed
        self._watcher.on_connected = self._on_watcher_connected
        self._watcher.on_disconnected = self._on_watcher_disconnected
        self._watcher.on_error = self._on_watcher_error
        self._watcher.on_overflow = self._on_watcher_overflow
        self._disconnected_roots: set[str] = set()  # 跟踪断连的目录，重连后补偿刷新

        # 心跳自动刷新（订阅刷新由 _apply_heartbeat_settings 控制启停）
        self._heartbeat = QTimer()
        self._heartbeat.timeout.connect(self._heartbeat_tick)

        self._build_ui()
        self._build_menu()
        self._build_statusbar()
        self._wire_signals()

        # 启动时：若已有索引则直接用于匹配，否则提示用户扫描
        self._load_nas_folders_from_index()
        if self._nas_folders:
            # 延迟到事件循环空闲再跑匹配——让窗口先完整绘制，用户第一帧即见 UI
            QTimer.singleShot(0, self._run_match)
            # 启动已确认项目的实时监控（延迟到索引加载后）
            QTimer.singleShot(100, self._start_watching_projects)
        elif not (config_manager.local_roots and config_manager.nas_roots):
            QMessageBox.information(
                self, "欢迎", "首次使用请先「设置」本地根目录与服务器根目录，\n"
                "然后点击「扫描并缓存服务器」建立索引。"
            )

        # 应用心跳自动刷新设置（若启用则在后台按间隔轮询当前项目的服务器内容）
        self._apply_heartbeat_settings()

        # 应用面板模式（服务器+本地 / 仅本地 / 仅服务器）
        self._apply_project_mode()

    # --------------------------- UI 构建 ---------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # === 顶部工具条 ===
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 8)
        bar.setSpacing(8)
        self.btn_index = QPushButton("扫描服务器")
        self.btn_match = QPushButton("重新匹配")
        self.btn_match.setObjectName("primary")
        self.btn_settings = QPushButton("设置")
        self.btn_qc = QPushButton("QC检测")
        self.btn_pause = QPushButton("暂停")
        self.btn_pause.setVisible(False)
        self.btn_pause.setObjectName("danger")
        bar.addWidget(self.btn_index)
        bar.addWidget(self.btn_match)
        bar.addWidget(self.btn_settings)
        bar.addWidget(self.btn_qc)
        bar.addWidget(self.btn_pause)
        bar.addStretch(1)
        root.addLayout(bar)

        # === 三栏 ===
        self.left = LeftSidebar()
        self.middle = MiddlePanel()
        self.right = RightPanel()
        for w in (self.left, self.middle, self.right):
            w.setMinimumWidth(140)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.left)
        splitter.addWidget(self.middle)
        splitter.addWidget(self.right)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([260, 460, 460])
        self.splitter = splitter
        root.addWidget(splitter, 1)

    def _build_menu(self):
        menubar = self.menuBar()
        fmenu = menubar.addMenu("文件(&F)")
        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(self._open_settings)
        act_exit = QAction("退出", self)
        act_exit.triggered.connect(self.close)
        fmenu.addAction(act_settings)
        fmenu.addSeparator()
        fmenu.addAction(act_exit)

        omenu = menubar.addMenu("操作(&O)")
        act_index = QAction("扫描并缓存服务器", self)
        act_index.triggered.connect(self._start_index)
        act_match = QAction("重新匹配", self)
        act_match.triggered.connect(self._run_match)
        omenu.addAction(act_index)
        omenu.addAction(act_match)

        hmenu = menubar.addMenu("帮助(&H)")
        act_manual = QAction("用户手册", self)
        act_manual.triggered.connect(self._open_manual)
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._about)
        hmenu.addAction(act_manual)
        hmenu.addAction(act_about)

    def _build_statusbar(self):
        sb = self.statusBar()
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumWidth(180)
        sb.addPermanentWidget(self._progress)

    def _wire_signals(self):
        self.btn_index.clicked.connect(self._start_index)
        self.btn_match.clicked.connect(self._run_match)
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_qc.clicked.connect(self._open_qc_detection)
        self.btn_pause.clicked.connect(self._toggle_pause)

        self.left.project_selected.connect(self._on_project_selected)
        self.left.refresh_requested.connect(self._on_refresh_requested)
        self.left.projects_changed.connect(self._on_projects_changed)

        self.right.matched_changed.connect(self._on_matched_changed)
        self.right.need_rematch.connect(self._on_need_rematch)

        # 双向发送到对侧（右键菜单「发送到对侧」= 复制到对侧当前目录）
        self.middle.view.send_to_peer = lambda paths: self.right._on_files_dropped(paths, None, False)
        self.right.view.send_to_peer = lambda paths: self.middle._on_files_dropped(paths, None, False)

        # 快捷键
        self.addAction(self._shortcut("Ctrl+F", self._focus_search))
        self.addAction(self._shortcut("Ctrl+S", self._open_settings))

    # --------------------------- 索引调度 ---------------------------
    def _start_index(self):
        roots = config_manager.nas_roots
        if not roots:
            QMessageBox.warning(self, "未配置服务器", "请先在「设置」中添加至少一个服务器根目录。")
            return
        if self._index_worker and self._index_worker.isRunning():
            return
        self._pause_event.clear()
        self._stop_event.clear()
        self.btn_pause.setVisible(True)
        self.btn_pause.setText("暂停")
        self._progress.setVisible(True)
        self._status_msg("正在快速扫描项目级目录…（可暂停）")

        self._index_worker = IndexWorker(roots, self._pause_event, self._stop_event, fast=True)
        self._wm.register("index", self._index_worker)
        self._index_worker.progress.connect(
            lambda d, f, p: self._status_msg(f"索引中… 目录 {d} / 文件 {f}" + (f"  {p}" if p else ""))
        )
        self._index_worker.finished.connect(self._on_index_finished)
        self._index_worker.start()

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.btn_pause.setText("暂停")
            self._status_msg("继续索引…")
        else:
            self._pause_event.set()
            self.btn_pause.setText("继续")
            self._status_msg("已暂停，点击继续…")

    def _open_qc_detection(self):
        """打开 QC 检测窗口（工具栏按钮，不预载文件，线程数可用底部控件调整）。"""
        from ..qc_bridge import open_qc_detection
        open_qc_detection()

    def _on_index_finished(self, stats: dict):
        self._progress.setVisible(False)
        self.btn_pause.setVisible(False)
        self._load_nas_folders_from_index()
        self._status_msg(
            f"索引完成：目录 {stats['dirs']} 个，文件 {stats['files']} 个，"
            f"耗时 {stats['elapsed']}s"
        )
        # 索完成后自动匹配
        self._run_match()
        # 对新加项目启动后台深度扫描
        self._start_deep_scan()
        # 启动已确认项目的实时监控
        self._start_watching_projects()

    def _start_deep_scan(self):
        """后台逐一深度扫描已确认路径的项目。"""
        projects = config_manager.projects
        roots = [p["confirmed_nas_path"] for p in projects if p.get("confirmed_nas_path")]
        if not roots:
            return
        try:
            if self._deep_scan_worker and self._deep_scan_worker.isRunning():
                return
        except RuntimeError:
            self._deep_scan_worker = None
            return
        self._deep_scan_worker = DeepScanWorker(roots)
        self._wm.register("deep_scan", self._deep_scan_worker)
        self._deep_scan_worker.progress.connect(
            lambda d, t, p: self._status_msg(f"深度扫描项目… {d}/{t} {os.path.basename(p)}")
        )
        self._deep_scan_worker.finished.connect(
            lambda s: self._status_msg(
                f"深度扫描完成：目录 {s['dirs']}，文件 {s['files']}"
            )
        )
        self._deep_scan_worker.finished.connect(self._on_deep_scan_done)
        self._deep_scan_worker.start()

    def _on_deep_scan_done(self, stats=None):
        """DeepScanWorker 完成后清理引用，防止 C++ 对象已销毁后访问崩溃。"""
        if self._deep_scan_worker:
            self._wm.unregister("deep_scan")
            self._deep_scan_worker.deleteLater()
            self._deep_scan_worker = None

    def _load_nas_folders_from_index(self):
        try:
            self._nas_folders = nas_indexer.indexer.query_all_folders()
        except Exception:  # noqa: BLE001
            self._nas_folders = []
        # NAS 断连检测（仅检查根目录，不遍历条目）
        for root in config_manager.nas_roots:
            if root and not os.path.isdir(root):
                self._status_msg(f"服务器不可访问：{root}")

    # --------------------------- 增量刷新（刷新按钮 / 心跳共用） ---------------------------
    def _refresh_server_project(self, root: str, on_done=None):
        """统一入口：增量刷新某个项目服务器子树（含子文件夹）。
        由服务器面板「刷新」按钮与心跳定时器共用，避免并发写同一索引连接。"""
        if not root:
            return
        if self._refresh_worker and self._refresh_worker.isRunning():
            return  # 已有刷新在跑，跳过
        if self._index_worker and self._index_worker.isRunning():
            return  # 全量索引重建中，跳过
        try:
            if self._deep_scan_worker and self._deep_scan_worker.isRunning():
                return  # 深度扫描中，跳过（同样写全局索引单例，避免跨线程写同一连接）
        except RuntimeError:
            self._deep_scan_worker = None
        self._status_msg(f"增量刷新服务器：{root}")
        self._refresh_worker = RefreshIndexWorker(root)
        self._wm.register("refresh", self._refresh_worker)
        self._refresh_worker.finished.connect(
            lambda r: self._on_refresh_server_done(r, on_done)
        )
        self._refresh_worker.error.connect(
            lambda r, msg: self._on_refresh_server_error(r, msg, on_done)
        )
        self._refresh_worker.start()

    def _on_refresh_server_done(self, root: str, on_done):
        self._refresh_worker = None
        try:
            if on_done:
                on_done(root)
        except Exception:
            try:
                from ..crash_handler import log_exception

                log_exception("刷新完成回调异常")
            except Exception:
                pass

    def _on_refresh_server_error(self, root: str, msg: str, on_done):
        self._refresh_worker = None
        self._status_msg(f"服务器刷新失败：{msg}")
        if on_done:
            on_done(root)

    # --------------------------- 心跳自动刷新 ---------------------------
    def _heartbeat_tick(self):
        """按间隔自动增量刷新「当前选中项目」的服务器内容（含子文件夹）。"""
        if self._index_worker and self._index_worker.isRunning():
            return
        if not self._current_project:
            return
        root = self._current_project.get("confirmed_nas_path")
        if not root:
            return
        self._refresh_server_project(root, on_done=self._after_heartbeat)

    def _after_heartbeat(self, root: str):
        """心跳刷新完成：若仍选中同一项目，则刷新右栏当前视图。"""
        try:
            if self._current_project and self._current_project.get("confirmed_nas_path") == root:
                self.right._after_server_refresh(root)
        except Exception:
            try:
                from ..crash_handler import log_exception

                log_exception("心跳刷新后处理异常")
            except Exception:
                pass
        self._status_msg(f"心跳刷新完成：{root}")

    def _apply_heartbeat_settings(self):
        """根据设置启停心跳定时器。"""
        enabled = config_manager.auto_refresh_enabled
        interval = max(5, int(config_manager.auto_refresh_interval)) * 1000
        self._heartbeat.setInterval(interval)
        if enabled:
            if not self._heartbeat.isActive():
                self._heartbeat.start()
            self._status_msg(f"已启用自动刷新（每 {interval // 1000} 秒）")
        else:
            self._heartbeat.stop()

    def _apply_project_mode(self):
        """根据配置的面板模式显示/隐藏中栏（本地）和右栏（服务器）。"""
        mode = config_manager.project_mode
        if mode == "local_only":
            self.middle.setVisible(True)
            self.right.setVisible(False)
        elif mode == "server_only":
            self.middle.setVisible(False)
            self.right.setVisible(True)
        else:  # "both"
            self.middle.setVisible(True)
            self.right.setVisible(True)

    # --------------------------- Watcher 实时监控 ---------------------------
    def _start_watching_projects(self):
        """索引完成后，启动监控所有已确认路径的项目。"""
        projects = config_manager.projects
        roots = set()
        for p in projects:
            path = p.get("confirmed_nas_path", "")
            if path and os.path.isdir(path):
                roots.add(path.rstrip("/\\"))
        # 停止不再需要监控的目录
        for root in self._watcher.watching_roots():
            if root not in roots:
                self._watcher.unwatch(root)
        # 启动新的监控
        for root in roots:
            self._watcher.watch(root)
        if roots:
            self._status_msg(f"已启动实时监控：{len(roots)} 个项目目录")

    def _on_watcher_changed(self, root: str, affected_dirs: list[str]):
        """Watcher 检测到目录变更：增量更新索引 + 刷新当前面板（若受影响）。"""
        # 增量更新索引
        stats = nas_indexer.indexer.refresh_dirs(affected_dirs)
        if any(stats.values()):
            self._status_msg(
                f"实时同步：+{stats['added']} ~{stats['updated']} -{stats['removed']} 项"
            )
        # 判断当前面板是否需要刷新
        current = self.right._current_root
        if not current:
            return
        current_norm = current.rstrip("/\\")
        for d in affected_dirs:
            d_norm = d.rstrip("/\\")
            # 受影响的目录是当前查看的目录，或是其子目录
            if d_norm == current_norm or d_norm.startswith(current_norm + "\\") or d_norm.startswith(current_norm + "/"):
                # 同步从索引读取，避免 ListWorker 线程开销
                try:
                    entries = nas_indexer.indexer.list_children(current)
                    if entries:
                        self.right.path_label.setText(current)
                        self.right.view.set_entries(entries)
                        self.right.status.setText(f"共 {len(entries)} 项")
                        return
                except Exception:  # noqa: BLE001
                    pass
                self.right._load_contents(current)
                return

    def _on_watcher_connected(self, root: str):
        """Watcher 成功连接到一个目录。"""
        was_disconnected = root in self._disconnected_roots
        self._disconnected_roots.discard(root)
        if was_disconnected:
            # 重连后补偿刷新：断连期间的事件可能已丢失，扫描一级子目录
            self._status_msg(f"监控已恢复，正在补偿刷新：{os.path.basename(root)}")
            self._recovery_refresh(root)
        else:
            self._status_msg(f"监控已连接：{os.path.basename(root)}")

    def _on_watcher_disconnected(self, root: str):
        """Watcher 与目录的连接丢失。"""
        self._disconnected_roots.add(root)
        self._status_msg(f"监控断开（将自动重连）：{os.path.basename(root)}")

    def _on_watcher_error(self, root: str, msg: str):
        """Watcher 遇到错误。"""
        import logging
        logging.getLogger("MediaNexus.Watcher").warning(f"监控错误 {root}: {msg}")

    def _on_watcher_overflow(self, root: str):
        """Watcher 事件缓冲区溢出：扫描一级子目录补偿丢失的事件。"""
        self._status_msg(f"事件过多，补偿刷新：{os.path.basename(root)}")
        self._recovery_refresh(root)

    def _recovery_refresh(self, root: str):
        """补偿刷新：扫描 root 的一级子目录，补扫断连/溢出期间可能丢失的变更。"""
        try:
            # 先刷新 root 自身
            nas_indexer.indexer.refresh_dir(root)
            # 再扫描其一级子目录
            children = nas_indexer.indexer.list_children(root)
            sub_dirs = [c["path"] for c in children if c["is_dir"]]
            if sub_dirs:
                nas_indexer.indexer.refresh_dirs(sub_dirs)
            # 若当前面板显示的是该 root 或其子目录，刷新面板
            current = self.right._current_root
            if current and current.rstrip("/\\").startswith(root.rstrip("/\\")):
                self.right._load_contents(current)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("MediaNexus.Watcher").warning(f"补偿刷新失败 {root}: {e}")

    # --------------------------- 匹配调度 ---------------------------
    def _run_match(self, project_names: list[str] | None = None):
        if not self._nas_folders:
            QMessageBox.information(
                self, "需先索引", "尚未建立服务器索引或索引为空。\n请先点击「扫描并缓存服务器」。"
            )
            return
        if self._match_worker and self._match_worker.isRunning():
            return
        if project_names:
            self._status_msg(f"匹配中… {', '.join(project_names)}")
        else:
            self._status_msg("匹配中…")
        self._progress.setVisible(True)
        self._match_worker = MatchWorker(
            config_manager.local_roots,
            self._nas_folders,
            config_manager.match_threshold,
            project_names=project_names,
        )
        self._wm.register("match", self._match_worker)
        # 实时显示匹配进度（每个项目匹配完即更新状态栏）
        self._match_worker.project_ready.connect(self._on_project_matched)
        self._match_worker.progress.connect(
            lambda c, t, n: self._status_msg(f"匹配中… {c}/{t}  ({n})")
        )
        self._match_worker.finished.connect(self._on_match_finished)
        self._match_worker.start()

    def _on_match_finished(self, total: int):
        self.left.refresh()
        self._progress.setVisible(False)
        self._status_msg(f"匹配完成，共 {total} 个项目")
        self._match_worker = None
        # 自动选中第一个
        if total:
            if self._current_project:
                current_name = self._current_project.get("local_name", "")
                if current_name:
                    self._on_project_selected(current_name)
                    return
            self.left.select_first()

    def _on_project_matched(self, project: dict):
        """单个项目匹配完成时实时更新状态栏（不再丢失 project_ready 信号）。"""
        name = project.get("local_name", "")
        status = project.get("status", "")
        cands = len(project.get("nas_candidates", []))
        confirmed = project.get("confirmed_nas_path", "")
        if confirmed:
            self._status_msg(f"已确认 {name} → {confirmed}")
        elif cands:
            self._status_msg(f"已匹配 {name} → {cands} 个候选（{status}）")
        else:
            self._status_msg(f"已处理 {name}（{status}）")

    # --------------------------- 项目选择 ---------------------------
    def _on_project_selected(self, name: str):
        if not name:
            self._current_project = None
            self.middle.load("", no_local=False)
            self.right.load({"local_name": "", "local_path": "",
                             "nas_candidates": [], "confirmed_nas_path": "",
                             "status": "unmatched"})
            if config_manager.project_mode == "both":
                self.middle.setVisible(True)
                self.right.setVisible(True)
            return
        proj = config_manager.get_project(name)
        if not proj:
            return
        self._current_project = proj
        local_path = proj.get("local_path", "")
        confirmed = proj.get("confirmed_nas_path", "")
        self.middle.load(local_path, no_local=not local_path)
        self.right.load(proj)

        # 双索引模式：始终同时显示本地与服务器两栏。
        # 某一侧为空时由对应面板自身展示提示文字（如 MiddlePanel 的「无本地项目文件夹」
        # +「新建项目文件夹」按钮、RightPanel 的「未确认服务器目录」提示），不再隐藏面板，
        # 避免选中纯服务器项目时丢失本地栏的「新建项目文件夹」入口。
        if config_manager.project_mode == "both":
            self.middle.setVisible(True)
            self.right.setVisible(True)
        # 仅本地/仅服务器模式由全局 _apply_project_mode 控制，这里不覆盖

    def _on_projects_changed(self):
        """项目增删后：若当前选中的项目已被删除，清空面板。"""
        if self._current_project:
            name = self._current_project.get("local_name", "")
            if name and not config_manager.get_project(name):
                self._current_project = None
                self.middle.load("")
                self.right.load({"local_name": "", "local_path": "",
                                 "nas_candidates": [], "confirmed_nas_path": "",
                                 "status": "unmatched"})


    def _on_matched_changed(self):
        config_manager.save()
        self.left.refresh()
        # 刷新右栏当前项目状态显示
        if self._current_project:
            name = self._current_project.get("local_name", "")
            updated = config_manager.get_project(name)
            if updated:
                self._current_project = updated
                self.right.load(updated)
        # 项目确认路径变更后，更新监控列表
        self._start_watching_projects()

    def _on_refresh_requested(self, name: str):
        """侧栏「重新匹配此项目」→ 弹出候选选择对话框。"""
        if not name:
            return
        proj = config_manager.get_project(name)
        if not proj:
            return
        import os
        from ..matcher import match_project
        from .select_match_dialog import SelectMatchDialog

        nas_roots = config_manager.nas_roots
        if not nas_roots or not self._nas_folders:
            QMessageBox.information(self, "无服务器", "尚未配置服务器根目录或索引为空。\n请先在「设置」配置并在「扫描服务器」建立索引。")
            return
        project_candidates = [
            f for f in self._nas_folders
            if any(os.path.dirname(f).rstrip("/\\") == r.rstrip("/\\") for r in nas_roots)
        ]
        excluded = config_manager.settings.get("excluded", {}).get(name, [])
        candidates = match_project(
            proj.get("name") or os.path.basename(name.rstrip("/\\")),
            project_candidates, threshold=config_manager.match_threshold,
            top_n=20, excluded=excluded,
        )
        dlg = SelectMatchDialog(proj, candidates, self)
        dlg.matched_changed.connect(self._on_matched_changed)
        dlg.exec()

    def _on_need_rematch(self, name: str):
        # 排除后仅重排当前项目候选，避免触发全量匹配
        self._run_match([name])

    def _status_msg(self, msg: str):
        """状态栏消息。"""
        self.statusBar().showMessage(msg)

    # --------------------------- 设置 / 帮助 ---------------------------
    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.config_saved = self._after_settings_saved
        dlg.exec()

    def _after_settings_saved(self):
        self._apply_heartbeat_settings()
        self._apply_project_mode()
        self._start_watching_projects()  # 设置变更可能影响监控目录
        self._status_msg("设置已保存。建议点击「扫描并缓存服务器」刷新索引。")

    def _open_manual(self):
        # 内嵌网页式用户手册（QWebEngineView，缺失时回退 QTextBrowser）
        from utils.docs_viewer import open_manual
        open_manual(self)

    def _about(self):
        from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QDialogButtonBox, QScrollArea
        dlg = QDialog(self)
        dlg.setWindowTitle(f"关于 {APP_NAME}")
        dlg.setMinimumSize(460, 560)
        dlg.setStyleSheet("QDialog { background-color: #FFFFFF; } QLabel { color: #1F2937; }")
        v = QVBoxLayout(dlg)
        v.setSpacing(10)
        v.setContentsMargins(24, 20, 24, 20)

        # 标题
        title = QLabel(f"<h2 style='margin:0; text-align:center;'>{APP_NAME}</h2>"
                       f"<p style='text-align:center; color:#6B7280; margin:2px;'>v{APP_VERSION}</p>")
        title.setTextFormat(Qt.RichText)
        v.addWidget(title)

        # 功能说明（滚动区）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QLabel(
            "<div style='line-height:1.8; font-size:13px;'>"
            "<h3 style='color:#2563EB;'>软件功能</h3>"
            "<p><b>项目管理</b><br>"
            "· 本地+服务器双索引：自动模糊匹配本地与服务器同名项目<br>"
            "· 仅本地模式：只管理本地素材<br>"
            "· 仅服务器模式：只管理服务器素材<br>"
            "· 右键项目可重新匹配、重命名、指定本地目录、删除</p>"
            "<p><b>文件浏览</b><br>"
            "· 三栏布局：项目导航 / 本地内容 / 服务器内容<br>"
            "· 双击文件夹进入子目录，上级按钮返回<br>"
            "· 拖放复制/移动文件，跨栏拖放自动复制<br>"
            "· 右键菜单：复制、剪切、粘贴、删除、重命名、新建、刷新<br>"
            "· 快捷键：Ctrl+C/X/V、Ctrl+A、F2、Del</p>"
            "<p><b>服务器索引</b><br>"
            "· 快速扫描项目级目录，添加后后台深度扫描<br>"
            "· 心跳自动刷新当前项目内容（可配置间隔）<br>"
            "· 增量刷新不阻塞操作</p>"
            "<p><b>QC 视频检测</b><br>"
            "· 一键检测黑帧、夹帧/跳帧、黑边、静音<br>"
            "· 右键文件或文件夹直接发起检测<br>"
            "· 多版本对比：同名视频跨文件夹横向对比<br>"
            "· 检测预设可在设置中管理，参数可视化编辑</p>"
            "<p><b>其他</b><br>"
            "· 缩略图/列表双视图切换<br>"
            "· 搜索过滤、多排序方式<br>"
            "· 配置即时落盘，重启不丢失</p>"
            "</div>"
        )
        content.setWordWrap(True)
        content.setTextFormat(Qt.RichText)
        scroll.setWidget(content)
        v.addWidget(scroll, 1)

        # 作者信息
        info = QLabel(
            "<hr style='border:none; border-top:1px solid #E5E7EB; margin:8px 0;'>"
            "<p style='text-align:center; font-size:12px; color:#6B7280;'>"
            f"作者：Zxgaoq<br>"
            f"BUG 反馈：3096959163@qq.com<br>"
            f"联系作者：AboutZxgaoq"
            "</p>"
        )
        info.setTextFormat(Qt.RichText)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(info)

        # OK 按钮
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        v.addWidget(btns)
        dlg.exec()

    # --------------------------- 快捷键辅助 ---------------------------
    def _shortcut(self, key: str, slot) -> QAction:
        act = QAction(self)
        act.setShortcut(QKeySequence(key))
        act.triggered.connect(slot)
        return act

    def _focus_search(self):
        self.left.search.setFocus()
        self.left.search.selectAll()

    def refresh_current(self):
        """供文件列表右键「刷新」调用：刷新中栏与右栏当前目录。"""
        self.middle.refresh_current()
        self.right.refresh_current()

    def keyPressEvent(self, event):
        # ↑/↓ 在侧栏项目间切换；Enter 确认当前服务器匹配
        if event.key() == Qt.Key_Up:
            self._move_selection(-1)
        elif event.key() == Qt.Key_Down:
            self._move_selection(1)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._current_project:
                self.right._confirm()
        else:
            super().keyPressEvent(event)

    def _move_selection(self, delta: int):
        lst = self.left.list
        if lst.count() == 0:
            return
        row = lst.currentRow()
        row = 0 if row < 0 else row
        nrow = max(0, min(lst.count() - 1, row + delta))
        item = lst.item(nrow)
        if item is not None:
            lst.setCurrentRow(nrow)
            self._on_project_selected(item.data(Qt.UserRole))

    def closeEvent(self, event):
        # ── 立即给用户反馈 ──
        self.statusBar().showMessage("正在停止…")

        # ── 第一步：断开 watcher 回调，防止队列中的信号触发 refresh_dirs 等耗时操作 ──
        self._watcher.on_changed = None
        self._watcher.on_connected = None
        self._watcher.on_disconnected = None
        self._watcher.on_error = None
        self._watcher.on_overflow = None

        # ── 第二步：停止心跳 + 设置全局停止信号 ──
        self._heartbeat.stop()
        self._stop_event.set()

        # ── 第三步：停止实时监控（QThread ~300ms 退出，daemon 线程随进程消亡） ──
        self._watcher.stop_all()

        # ── 第四步：处理残余 UI 事件（此时 watcher 回调已断开，不会触发耗时操作） ──
        QApplication.processEvents()

        # ── 第五步：面板内的 copy worker（未注册到 _wm，单独处理） ──
        for w in (self.middle, self.right):
            for attr in ("_copy_worker",):
                worker = getattr(w, attr, None)
                if worker and worker.isRunning():
                    worker.requestInterruption()
            view = getattr(w, "view", None)
            if view and hasattr(view, "_stop_thumbnails"):
                view._stop_thumbnails()

        # ── 第六步：通过 WorkerManager 统一停止所有主 worker ──
        self._wm.stop_all(timeout_per_worker=1500)

        super().closeEvent(event)


# ── 全局滚轮拦截（禁止 QComboBox/QSpinBox/QDoubleSpinBox 响应滚轮）──
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox
_WHL_WIDGETS = (QComboBox, QSpinBox, QDoubleSpinBox)

class _WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if isinstance(obj, _WHL_WIDGETS) and event.type() == QEvent.Type.Wheel:
            # QComboBox: 弹出列表时滚轮正常选择项；关闭时转载到父级滚动。
            # QSpinBox/QDoubleSpinBox: 永远不通过滚轮改值，转载给父级。
            forward = True
            if isinstance(obj, QComboBox):
                forward = not obj.view().isVisible()
            if forward:
                app = QApplication.instance()
                if app:
                    app.sendEvent(obj.parent(), event)
                return True
        return super().eventFilter(obj, event)


def run_app():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app.installEventFilter(_WheelBlocker(app))
    # 解决高 DPI 下模糊
    # 应用级图标（任务栏 / 关于对话框 / 弹窗统一显示）—— 透明版 Logo
    logo_path = resource_path("assets/logo.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    # 首次启动引导（仅安装后第一次出现，选完才进入主界面）
    from utils.onboarding import run_onboarding
    run_onboarding()

    # 版本升级提示：检测到 config 中版本号与当前 APP_VERSION 不一致时弹窗
    try:
        from ..config_manager import config_manager
        from ..constants import APP_VERSION
        stored_ver = config_manager.settings.get("app_version", "")
        if stored_ver and stored_ver != APP_VERSION:
            QMessageBox.information(
                None, f"影枢 已更新到 v{APP_VERSION}",
                f"已从 v{stored_ver} 更新到 v{APP_VERSION}。\n\n"
                "新增：QC 检测结果缓存、SQLite 性能优化、缓存管理面板等。\n"
                "您的所有配置和项目数据已完整保留。"
            )
        config_manager.settings["app_version"] = APP_VERSION
        config_manager.save()
    except Exception:
        pass

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
