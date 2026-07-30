# -*- coding: utf-8 -*-
"""
ProjectSync Studio - 设置对话框（多选项卡版本）
  * 通用：项目运行模式 + 心跳自动刷新
  * 项目：本地/NAS根目录、匹配阈值、忽略关键词（根据模式显示）
  * 检测：预设管理
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config_manager import config_manager
from .preset_panel import PresetParamPanel
from utils.config import PARAMETER_GUIDE
from utils.ffmpeg_manager import FFmpegManager, DEFAULT_DOWNLOAD_URL
from utils.storage_manager import StorageManager


class SettingsDialog(QDialog):
    config_saved = None  # 由主窗口绑定

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置 - MediaSync")
        self.resize(680, 620)
        self._mode_before = config_manager.project_mode
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # ═══════════════════ 通用 ═══════════════════
        general_tab = QWidget()
        gen_scroll = QScrollArea()
        gen_scroll.setWidgetResizable(True)
        gen_container = QWidget()
        gen_layout = QVBoxLayout(gen_container)
        gen_layout.setContentsMargins(16, 16, 16, 16)
        gen_layout.setSpacing(12)

        # ── 项目运行模式 ──
        gen_layout.addWidget(QLabel("项目管理方式"))
        gen_layout.addWidget(QLabel("根据你的项目文件位置选择"))
        mode_group = QGroupBox()
        mode_layout = QVBoxLayout(mode_group)
        self.mode_group = QButtonGroup(self)
        self.radio_both = QRadioButton("本地+服务器双索引（默认，完整功能）")
        self.radio_local = QRadioButton("仅本地（只管理本地项目文件）")
        self.radio_server = QRadioButton("仅服务器（只管理服务器项目文件）")
        self.radio_both.setToolTip("同时索引本地与服务器（NAS）项目，功能最完整（默认）。")
        self.radio_local.setToolTip("只管理本地项目文件，不连接服务器，适合纯本地剪辑。")
        self.radio_server.setToolTip("只管理服务器（NAS）项目文件，不显示本地目录，适合只看素材。")
        for rb in [self.radio_both, self.radio_local, self.radio_server]:
            self.mode_group.addButton(rb)
            mode_layout.addWidget(rb)
        self.mode_group.setId(self.radio_both, 0)
        self.mode_group.setId(self.radio_local, 1)
        self.mode_group.setId(self.radio_server, 2)
        gen_layout.addWidget(mode_group)

        gen_layout.addSpacing(8)

        # ── 心跳 ──
        gen_layout.addWidget(QLabel("服务器自动刷新（心跳轮询）"))
        gen_layout.addWidget(QLabel(
            "启用后，软件将按设定间隔自动增量刷新当前项目的服务器内容（含子文件夹）。"
        ))
        self.auto_refresh_chk = QCheckBox("启用自动刷新（心跳轮询服务器）")
        self.auto_refresh_chk.setToolTip(
            "开启后，按设定间隔自动增量刷新当前项目的服务器内容，无需手动重新扫描。"
        )
        gen_layout.addWidget(self.auto_refresh_chk)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("轮询间隔:"))
        self.auto_interval = QSpinBox()
        self.auto_interval.setRange(5, 3600)
        self.auto_interval.setSuffix(" 秒")
        self.auto_interval.setToolTip("自动刷新的时间间隔（秒）。越短越及时，但会更频繁访问服务器。")
        interval_row.addWidget(self.auto_interval)
        interval_row.addStretch(1)
        gen_layout.addLayout(interval_row)

        gen_layout.addStretch(1)
        gen_scroll.setWidget(gen_container)
        tabs.addTab(gen_scroll, "通用")

        # ═══════════════════ 项目 ═══════════════════
        project_tab = QWidget()
        proj_layout = QVBoxLayout(project_tab)
        proj_layout.setContentsMargins(16, 16, 16, 16)
        proj_layout.setSpacing(8)

        # 本地根目录
        self.local_group = QGroupBox("本地项目根目录")
        self.local_group.setToolTip("本地项目所在的根目录列表；其下每个子文件夹会被视为一个项目。")
        local_vbox = QVBoxLayout(self.local_group)
        self.local_list = QListWidget()
        self.local_list.setToolTip("已添加的本地项目根目录；右键列表项可单独操作。")
        local_vbox.addWidget(self.local_list, 1)
        h1 = QHBoxLayout()
        self.local_edit = QLineEdit()
        self.local_edit.setPlaceholderText(r"例如 D:\项目 或 Z:\本地素材")
        self.local_edit.setToolTip("输入本地项目根目录路径，点「添加」加入上方列表。")
        self.local_browse = QPushButton("浏览…")
        self.local_browse.clicked.connect(self._browse_local)
        self.local_add = QPushButton("添加")
        self.local_add.clicked.connect(self._add_local)
        self.local_del = QPushButton("删除选中")
        self.local_del.clicked.connect(self._del_local)
        h1.addWidget(self.local_edit, 1)
        h1.addWidget(self.local_browse)
        h1.addWidget(self.local_add)
        h1.addWidget(self.local_del)
        local_vbox.addLayout(h1)
        proj_layout.addWidget(self.local_group)

        # 服务器根目录
        self.nas_group = QGroupBox("服务器素材根目录")
        self.nas_group.setToolTip("服务器（NAS）素材根目录列表，用于与本地项目做模糊匹配。")
        nas_vbox = QVBoxLayout(self.nas_group)
        self.nas_list = QListWidget()
        self.nas_list.setToolTip("已添加的服务器（NAS）根目录；匹配结果会在主界面右栏展示。")
        nas_vbox.addWidget(self.nas_list, 1)
        h2 = QHBoxLayout()
        self.nas_edit = QLineEdit()
        self.nas_edit.setPlaceholderText(r"例如 \\NAS\Drama 或 Z:\素材")
        self.nas_edit.setToolTip("输入 UNC（\\\\server\\share）或盘符（Z:\\）路径，点「添加」加入列表。")
        self.nas_browse = QPushButton("浏览…")
        self.nas_browse.clicked.connect(self._browse_nas)
        self.nas_add = QPushButton("添加")
        self.nas_add.clicked.connect(self._add_nas)
        self.nas_del = QPushButton("删除选中")
        self.nas_del.clicked.connect(self._del_nas)
        h2.addWidget(self.nas_edit, 1)
        h2.addWidget(self.nas_browse)
        h2.addWidget(self.nas_add)
        h2.addWidget(self.nas_del)
        nas_vbox.addLayout(h2)
        proj_layout.addWidget(self.nas_group)

        # 匹配阈值
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("模糊匹配阈值 (0-100):"))
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 100)
        self.threshold.setToolTip(
            "模糊匹配相似度阈值（0-100）。越高越严格（误匹配少但可能漏匹配），"
            "越低越宽松（默认 80，项目名带版本 / 序号后缀时通常表现最佳）。"
        )
        h3.addWidget(self.threshold)
        h3.addStretch(1)
        proj_layout.addLayout(h3)

        # 忽略关键词
        proj_layout.addWidget(QLabel("忽略关键词（空格/逗号分隔，大小写不敏感）:"))
        self.ignore_edit = QTextEdit()
        self.ignore_edit.setMaximumHeight(80)
        self.ignore_edit.setToolTip(
            "索引时跳过含这些关键词的目录（如 OLD / 备份 / temp），让匹配更干净。"
            "多个词用空格或逗号分隔，大小写不敏感。"
        )
        proj_layout.addWidget(self.ignore_edit)

        proj_layout.addStretch(1)
        tabs.addTab(project_tab, "项目")

        # ═══════════════════ 检测 ═══════════════════
        detect_tab = QWidget()
        det_layout = QHBoxLayout(detect_tab)
        det_layout.setContentsMargins(16, 16, 16, 16)
        det_layout.setSpacing(8)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(QLabel("预设列表"))
        self.preset_list = QListWidget()
        self.preset_list.currentRowChanged.connect(self._on_preset_selected)
        self.preset_list.setToolTip("质检参数预设列表；标注 [活跃] 的为当前生效预设。")
        left_layout.addWidget(self.preset_list, 1)

        preset_btns = QVBoxLayout()
        preset_btns.setSpacing(4)
        self.btn_preset_activate = QPushButton("设为活跃")
        self.btn_preset_activate.clicked.connect(self._activate_preset)
        self.btn_preset_activate.setToolTip("将选中的预设设为当前活跃预设，质检时使用其参数。")
        self.btn_preset_save = QPushButton("保存参数")
        self.btn_preset_save.setObjectName("primary")
        self.btn_preset_save.clicked.connect(self._save_preset_params)
        self.btn_preset_save.setToolTip("把右侧「检测参数」面板的改动保存到选中预设。")
        self.btn_preset_add = QPushButton("新建预设")
        self.btn_preset_add.clicked.connect(self._add_preset)
        self.btn_preset_add.setToolTip("基于默认预设的参数新建一个自定义预设。")
        self.btn_preset_rename = QPushButton("重命名")
        self.btn_preset_rename.clicked.connect(self._rename_preset)
        self.btn_preset_rename.setToolTip("重命名选中的自定义预设（默认预设不可重命名）。")
        self.btn_preset_delete = QPushButton("删除")
        self.btn_preset_delete.clicked.connect(self._delete_preset)
        self.btn_preset_delete.setToolTip("删除选中的自定义预设（默认预设不可删除）。")
        for b in [self.btn_preset_activate, self.btn_preset_save,
                  self.btn_preset_add, self.btn_preset_rename, self.btn_preset_delete]:
            preset_btns.addWidget(b)
        left_layout.addLayout(preset_btns)
        left_widget.setMaximumWidth(220)
        det_layout.addWidget(left_widget)

        right_tabs = QTabWidget()
        self.param_panel = PresetParamPanel()
        right_tabs.addTab(self.param_panel, "检测参数")
        self.guide_text = QTextEdit()
        self.guide_text.setReadOnly(True)
        right_tabs.addTab(self.guide_text, "参数说明")
        det_layout.addWidget(right_tabs, 1)

        tabs.addTab(detect_tab, "检测")

        # ═══════════════════ 组件（FFmpeg） ═══════════════════
        comp_tab = QWidget()
        comp_layout = QVBoxLayout(comp_tab)
        comp_layout.setContentsMargins(16, 16, 16, 16)
        comp_layout.setSpacing(10)

        comp_layout.addWidget(QLabel("FFmpeg 组件（视频质检引擎依赖）"))
        comp_layout.addWidget(QLabel(
            "软件已内置 FFmpeg（完整版），无需下载即可使用所有功能。"
            "如需更新或手动指定其他版本，可在此下载或指定目录。"
        ))

        self.ff_status = QLabel("状态：检测中…")
        self.ff_status.setWordWrap(True)
        comp_layout.addWidget(self.ff_status)

        ff_btn_row = QHBoxLayout()
        self.ff_download_btn = QPushButton("下载 FFmpeg（可选）")
        self.ff_download_btn.setObjectName("primary")
        self.ff_download_btn.clicked.connect(self._ff_download)
        self.ff_locate_btn = QPushButton("手动指定文件夹…")
        self.ff_locate_btn.clicked.connect(self._ff_locate)
        ff_btn_row.addWidget(self.ff_download_btn)
        ff_btn_row.addWidget(self.ff_locate_btn)
        ff_btn_row.addStretch(1)
        comp_layout.addLayout(ff_btn_row)

        comp_layout.addWidget(QLabel("自定义下载地址（可选，例如国内镜像）："))
        self.ff_url_edit = QLineEdit()
        self.ff_url_edit.setPlaceholderText(DEFAULT_DOWNLOAD_URL)
        self.ff_url_edit.setToolTip("留空则使用内置默认下载地址；可替换为可达的镜像以加快下载。")
        comp_layout.addWidget(self.ff_url_edit)

        comp_layout.addSpacing(6)
        comp_layout.addWidget(QLabel(
            "提示：若下载失败（网络受限），可点击「手动指定文件夹」，"
            "选择已解压、且内含 ffmpeg.exe / ffprobe.exe 的目录即可。"
        ))
        comp_layout.addStretch(1)
        tabs.addTab(comp_tab, "组件")

        # ═══════════════════ 缓存 ═══════════════════
        cache_tab = QWidget()
        cache_scroll = QScrollArea()
        cache_scroll.setWidgetResizable(True)
        cache_container = QWidget()
        cache_layout = QVBoxLayout(cache_container)
        cache_layout.setContentsMargins(16, 16, 16, 16)
        cache_layout.setSpacing(8)

        cache_layout.addWidget(QLabel("缓存管理"))
        cache_layout.addWidget(QLabel("软件运行过程中产生的临时文件、日志和检测缓存，可在此查看和清理。"))

        # 缓存列表（每行：checkbox + 打开按钮）
        self._cache_rows: list[dict] = []
        self._cache_scroll = QScrollArea()
        self._cache_scroll.setWidgetResizable(True)
        self._cache_scroll.setMinimumHeight(180)
        self._cache_container = QWidget()
        self._cache_vlayout = QVBoxLayout(self._cache_container)
        self._cache_vlayout.setContentsMargins(0, 0, 0, 0)
        self._cache_vlayout.setSpacing(4)
        self._cache_vlayout.addStretch(1)
        self._cache_scroll.setWidget(self._cache_container)
        cache_layout.addWidget(self._cache_scroll, 1)

        # 操作按钮行
        btn_row = QHBoxLayout()
        self._cache_refresh_btn = QPushButton("刷新统计")
        self._cache_refresh_btn.clicked.connect(self._refresh_cache_info)
        self._cache_select_all_btn = QPushButton("全选")
        self._cache_select_all_btn.clicked.connect(self._cache_select_all)
        self._cache_clear_btn = QPushButton("清理所选缓存")
        self._cache_clear_btn.setObjectName("danger")
        self._cache_clear_btn.clicked.connect(self._cache_clear_selected)
        btn_row.addWidget(self._cache_refresh_btn)
        btn_row.addWidget(self._cache_select_all_btn)
        btn_row.addWidget(self._cache_clear_btn)
        btn_row.addStretch(1)
        cache_layout.addLayout(btn_row)

        self._cache_status = QLabel("")
        self._cache_status.setWordWrap(True)
        cache_layout.addWidget(self._cache_status)

        cache_layout.addStretch(1)
        cache_scroll.setWidget(cache_container)
        tabs.addTab(cache_scroll, "缓存")

        layout.addWidget(tabs)

        # ── 底部按钮 ──
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("保存")
        self.ok_btn.setObjectName("primary")
        self.cancel_btn = QPushButton("取消")
        self.ok_btn.clicked.connect(self._accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _load(self):
        mode = config_manager.project_mode
        if mode == "local_only":
            self.radio_local.setChecked(True)
        elif mode == "server_only":
            self.radio_server.setChecked(True)
        else:
            self.radio_both.setChecked(True)
        self.local_list.addItems(config_manager.local_roots)
        self.nas_list.addItems(config_manager.nas_roots)
        self.threshold.setValue(config_manager.match_threshold)
        self.ignore_edit.setPlainText(" ".join(config_manager.ignore_patterns))
        self.auto_refresh_chk.setChecked(config_manager.auto_refresh_enabled)
        self.auto_interval.setValue(config_manager.auto_refresh_interval)
        self._refresh_preset_list()
        self._apply_mode_visibility()
        self.ff_url_edit.setText(config_manager.ffmpeg_download_url)
        self._refresh_ff_status()
        # 缓存设置
        self._refresh_cache_info()

    def _apply_mode_visibility(self):
        """根据当前选中的 mode radio 显示/隐藏项目选项卡的路径组。"""
        if self.radio_local.isChecked():
            self.local_group.setVisible(True)
            self.nas_group.setVisible(False)
        elif self.radio_server.isChecked():
            self.local_group.setVisible(False)
            self.nas_group.setVisible(True)
        else:
            self.local_group.setVisible(True)
            self.nas_group.setVisible(True)

    def _accept(self):
        if self.radio_local.isChecked():
            mode = "local_only"
        elif self.radio_server.isChecked():
            mode = "server_only"
        else:
            mode = "both"

        # 模式变更提醒
        if mode != self._mode_before:
            reply = QMessageBox.warning(
                self, "切换运行模式",
                "切换项目管理方式将清空当前所有项目，是否继续？\n\n"
                "切换后你需要重新添加项目。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                # 用户取消切换，恢复 radio 到原模式
                self._mode_before = config_manager.project_mode
                if self._mode_before == "local_only":
                    self.radio_local.setChecked(True)
                elif self._mode_before == "server_only":
                    self.radio_server.setChecked(True)
                else:
                    self.radio_both.setChecked(True)
                self._apply_mode_visibility()
                return
            config_manager._data["projects"] = []
            config_manager.save()

        local = [self.local_list.item(i).text().strip()
                 for i in range(self.local_list.count())]
        local = [x for x in local if x]
        nas = [self.nas_list.item(i).text() for i in range(self.nas_list.count())]
        ignore = [
            x.strip() for x in self.ignore_edit.toPlainText().replace(",", " ").split()
            if x.strip()
        ]
        config_manager.project_mode = mode
        config_manager.local_roots = local
        config_manager.nas_roots = nas
        config_manager.match_threshold = self.threshold.value()
        config_manager.ignore_patterns = ignore
        config_manager.auto_refresh_enabled = self.auto_refresh_chk.isChecked()
        config_manager.auto_refresh_interval = self.auto_interval.value()
        if self.config_saved is not None:
            self.config_saved()
        self.accept()
        # 模式变更已在 _accept 中处理清空项目 + 确认
        self._mode_before = mode

    # ── 浏览 ──
    def _browse_local(self):
        d = QFileDialog.getExistingDirectory(self, "选择本地项目根目录")
        if d:
            self.local_edit.setText(d)

    def _browse_nas(self):
        d = QFileDialog.getExistingDirectory(self, "选择服务器素材根目录")
        if d:
            self.nas_edit.setText(d)

    # ── 本地根 CRUD ──
    def _add_local(self):
        p = self.local_edit.text().strip()
        if not p:
            return
        if self.local_list.findItems(p, Qt.MatchFlag.MatchExactly):
            return
        self.local_list.addItem(p)
        self.local_edit.clear()

    def _del_local(self):
        for it in self.local_list.selectedItems():
            self.local_list.takeItem(self.local_list.row(it))

    # ── NAS 根 CRUD ──
    def _add_nas(self):
        p = self.nas_edit.text().strip()
        if not p:
            return
        if not (p.startswith("\\\\") or p.startswith("//") or (len(p) >= 2 and p[1] == ":")):
            QMessageBox.warning(self, "格式提示", "建议填写 UNC 路径（\\\\server\\share）或盘符（Z:\\），\n也可先填写稍后在「扫描并缓存」时验证连通性。")
        if self.nas_list.findItems(p, Qt.MatchFlag.MatchExactly):
            return
        self.nas_list.addItem(p)
        self.nas_edit.clear()

    def _del_nas(self):
        for it in self.nas_list.selectedItems():
            self.nas_list.takeItem(self.nas_list.row(it))

    # ── 检测预设 ──────────────────────────────────────────────
    def _refresh_preset_list(self):
        self.preset_list.clear()
        active = config_manager.qc_active_preset
        presets = config_manager.qc_presets
        for key, preset in presets.items():
            label = preset.get("name", key)
            if key == active:
                label += "  [活跃]"
            self.preset_list.addItem(label)
            self.preset_list.item(self.preset_list.count() - 1).setData(Qt.ItemDataRole.UserRole, key)
        if self.preset_list.count() > 0:
            self.preset_list.setCurrentRow(0)

    def _on_preset_selected(self, row: int):
        if row < 0:
            return
        item = self.preset_list.item(row)
        if not item:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        preset = config_manager.qc_presets.get(key, {})
        thresholds = preset.get("thresholds", {})
        self.param_panel.load_thresholds(thresholds)
        self._update_guide(preset)

    def _save_preset_params(self):
        sel = self.preset_list.currentItem()
        if not sel:
            QMessageBox.warning(self, "提示", "请先选择一个预设")
            return
        key = sel.data(Qt.ItemDataRole.UserRole)
        presets = config_manager.qc_presets
        if key not in presets:
            return
        presets[key]["thresholds"] = self.param_panel.get_thresholds()
        config_manager.qc_presets = presets
        QMessageBox.information(self, "已保存", f"预设「{presets[key]['name']}」的参数已保存")

    def _add_preset(self):
        name, ok = QInputDialog.getText(self, "新建预设", "预设名称:")
        if not ok or not name.strip():
            return
        key = name.strip()
        if key in config_manager.qc_presets:
            QMessageBox.warning(self, "重复", f"预设「{key}」已存在")
            return
        from copy import deepcopy
        default_t = config_manager.qc_presets.get("default", {}).get("thresholds", {})
        config_manager.qc_presets[key] = {"name": key, "description": "用户自定义预设", "thresholds": deepcopy(default_t)}
        self._refresh_preset_list()

    def _delete_preset(self):
        sel = self.preset_list.currentItem()
        if not sel:
            return
        key = sel.data(Qt.ItemDataRole.UserRole)
        if key == "default":
            QMessageBox.warning(self, "不可删除", "默认预设不可删除")
            return
        reply = QMessageBox.question(self, "确认删除", f"删除预设「{key}」？")
        if reply != QMessageBox.StandardButton.Yes:
            return
        presets = config_manager.qc_presets.copy()
        del presets[key]
        config_manager.qc_presets = presets
        if config_manager.qc_active_preset == key:
            config_manager.qc_active_preset = "default"
        self._refresh_preset_list()

    def _activate_preset(self):
        sel = self.preset_list.currentItem()
        if not sel:
            return
        key = sel.data(Qt.ItemDataRole.UserRole)
        config_manager.qc_active_preset = key
        self._refresh_preset_list()

    def _rename_preset(self):
        sel = self.preset_list.currentItem()
        if not sel:
            return
        key = sel.data(Qt.ItemDataRole.UserRole)
        if key == "default":
            QMessageBox.warning(self, "不可重命名", "默认预设不可重命名")
            return
        presets = config_manager.qc_presets
        old = presets[key]["name"]
        name, ok = QInputDialog.getText(self, "重命名预设", "新名称:", text=old)
        if not ok or not name.strip():
            return
        presets[key]["name"] = name.strip()
        config_manager.qc_presets = presets
        self._refresh_preset_list()

    def _update_guide(self, preset: dict):
        lines = [f"# {preset.get('name', '预设')}"]
        desc = preset.get("description", "")
        if desc:
            lines.append(f"\n{desc}")
        lines.append("\n---\n")
        for key, guide in PARAMETER_GUIDE.items():
            lines.append(f"### {guide['name']}")
            lines.append(f"- **说明**：{guide['explanation']}")
            lines.append(f"- **推荐范围**：{guide['recommended']}")
            lines.append(f"- ⚠️ 调低风险：{guide['risk_low']}")
            lines.append(f"- ⚠️ 调高风险：{guide['risk_high']}")
            lines.append("")
        self.guide_text.setMarkdown("\n".join(lines))

    # ── FFmpeg 组件管理 ──────────────────────────────────────────
    def _refresh_ff_status(self):
        mgr = FFmpegManager()
        if mgr.is_available:
            ok, msg = mgr.verify()
            if ok:
                self.ff_status.setText(f"状态：✅ 已就绪\n{msg}\n路径：{mgr.ffmpeg_path}")
            else:
                self.ff_status.setText(f"状态：⚠️ 文件存在但不可用\n{msg}")
        else:
            self.ff_status.setText(
                "状态：❌ 未找到 FFmpeg\n"
                "视频质检功能需要 FFmpeg。请点击「下载 FFmpeg（可选）」或「手动指定文件夹」。"
            )

    def _ff_download(self):
        url = self.ff_url_edit.text().strip()
        if url:
            config_manager.ffmpeg_download_url = url
        mgr = FFmpegManager()
        dlg = QProgressDialog("正在获取 FFmpeg…", "取消", 0, 100, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()

        def cb(frac, status):
            dlg.setValue(int(frac * 100))
            dlg.setLabelText(status)
            QApplication.processEvents()
            return not dlg.wasCanceled()

        ok, msg = mgr.ensure_ffmpeg(progress_cb=cb)
        dlg.close()
        self._refresh_ff_status()
        if ok:
            QMessageBox.information(self, "完成", msg)
        else:
            QMessageBox.warning(
                self, "未能获取 FFmpeg",
                f"{msg}\n\n可改用「手动指定文件夹」选择已解压的 FFmpeg 目录。"
            )

    def _ff_locate(self):
        d = QFileDialog.getExistingDirectory(self, "选择含 ffmpeg.exe / ffprobe.exe 的文件夹")
        if not d:
            return
        mgr = FFmpegManager()
        if mgr.set_manual_dir(d):
            self._refresh_ff_status()
            QMessageBox.information(self, "已指定", f"已使用指定目录的 FFmpeg：\n{mgr.ffmpeg_path}")
        else:
            QMessageBox.warning(
                self, "目录无效",
                "该目录未同时包含 ffmpeg.exe 与 ffprobe.exe，请选择正确目录。"
            )

    # ── 缓存管理 ──
    def _refresh_cache_info(self):
        """刷新缓存统计列表。"""
        # 清除旧行
        while self._cache_vlayout.count() > 1:
            child = self._cache_vlayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._cache_rows.clear()
        storage = StorageManager()
        info = storage.get_all_cache_info()
        for item in info["items"]:
            text = (
                f"{item['name']}  —  {item['size_mb']:.1f} MB  ({item['file_count']} 个)"
                if item["size_mb"] > 0.001 else
                f"{item['name']}  —  空"
            )
            row = QWidget()
            rlay = QHBoxLayout(row)
            rlay.setContentsMargins(2, 2, 2, 2)
            rlay.setSpacing(8)
            chk = QCheckBox(text)
            chk.setToolTip(item["path"])
            chk.setChecked(item["size_mb"] > 0.001)
            btn = QPushButton("打开文件夹")
            btn.setFixedWidth(90)
            path = item["path"]
            btn.clicked.connect(lambda _=False, p=path: self._open_path(p))
            rlay.addWidget(chk, 1)
            rlay.addWidget(btn)
            # 在 stretch 之前插入
            self._cache_vlayout.insertWidget(self._cache_vlayout.count() - 1, row)
            self._cache_rows.append({"id": item["id"], "checkbox": chk, "path": path})
        self._cache_status.setText(
            f"总计可释放: {info['total_mb']:.1f} MB  |  {len(info['items'])} 类缓存"
        )

    def _cache_select_all(self):
        """全部勾选 / 取消勾选。"""
        all_checked = all(r["checkbox"].isChecked() for r in self._cache_rows)
        new_state = not all_checked
        for r in self._cache_rows:
            r["checkbox"].setChecked(new_state)

    def _cache_clear_selected(self):
        """清理勾选的缓存项。"""
        targets = {r["id"] for r in self._cache_rows if r["checkbox"].isChecked()}
        if not targets:
            QMessageBox.information(self, "提示", "没有选中的缓存项。")
            return
        ans = QMessageBox.question(
            self, "确认清理",
            f"确定要清理选中的 {len(targets)} 项缓存吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        storage = StorageManager()
        result = storage.clear_all_caches(targets)
        msg = f"已释放 {result['freed_mb']:.1f} MB"
        if result["errors"]:
            msg += f"\n{len(result['errors'])} 个错误"
        QMessageBox.information(self, "清理完成", msg)
        self._refresh_cache_info()

    def _open_path(self, path: str):
        """打开文件或文件夹所在位置。"""
        if os.path.isfile(path):
            os.startfile(os.path.dirname(path))
        elif os.path.isdir(path):
            os.startfile(path)
        else:
            QMessageBox.information(self, "提示", "该缓存位置不存在或尚未生成。")