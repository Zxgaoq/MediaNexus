# -*- coding: utf-8 -*-
"""
MediaNexus - 添加项目对话框

需求2：设置好本地与服务器路径并扫描索引后，点击「添加项目」弹出本对话框。
  * 左侧/表格列出「全部服务器的项目主文件夹」= 每个 NAS 根目录下的直接子文件夹
  * 顶部搜索框过滤服务器项目名
  * 每行复选框 + 一个「本地目录匹配」下拉：自动按名称模糊匹配出最佳候选，
    用户可自行改选其他本地目录，也可选「（无本地项目文件夹）」留空
  * 确认后返回 [(server_path, local_path), ...]，由调用方写入项目列表
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .. import indexer as nas_indexer
from .. import matcher
from ..config_manager import config_manager


class AddProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加项目 - 选择服务器项目")
        self.resize(740, 540)
        self._local_choices: dict[str, str] = {}  # server_path -> chosen local path
        self._local_only_rows: set[int] = set()   # 本地独有行的 row index
        self._build_ui()
        self._load_folders()

    # --------------------------- UI ---------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("搜索服务器项目:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("输入关键词过滤项目名…")
        self.search.textChanged.connect(self._apply_filter)
        top.addWidget(self.search, 1)
        layout.addLayout(top)

        self.hint = QLabel("")
        self.hint.setStyleSheet("color:#6B7280; font-size:11px;")
        layout.addWidget(self.hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["添加", "服务器项目", "本地目录匹配"])
        self.table.setColumnWidth(0, 48)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.ok_btn = QPushButton("确定")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    # --------------------------- 数据装载 ---------------------------
    def _load_folders(self):
        folders = self._collect_server_folders()
        local_pool = self._gather_local()
        if not folders and not local_pool:
            self.hint.setText(
                "尚未发现任何项目文件夹。请先在「设置」配置本地或服务器根目录，"
                "并点击「扫描服务器」建立索引。"
            )
            self.table.setRowCount(0)
            return
        if not folders:
            self.hint.setText(
                "尚未发现服务器项目主文件夹。请先在「设置」配置服务器根目录，"
                "并点击「扫描服务器」建立索引。下方仅显示本地项目。"
            )
        server_names = {os.path.basename(sp.rstrip("/\\")).lower() for sp in folders}
        # 排除已被服务器行自动匹配的本地文件夹
        matched_local_paths: set[str] = set()
        for sp in folders:
            cands = self._local_candidates(os.path.basename(sp.rstrip("/\\")), local_pool)
            if cands:
                matched_local_paths.add(cands[0][1])  # 最佳匹配路径
        unmatched_local = [
            (d, p) for d, p in local_pool
            if d.lower() not in server_names and p not in matched_local_paths
        ]

        total_rows = len(folders) + len(unmatched_local)
        self.hint.setText(
            f"共发现 {len(folders)} 个服务器项目主文件夹"
            + (f"，{len(unmatched_local)} 个本地独有项目" if unmatched_local else "")
            + "。勾选要添加的项目。"
        )
        self.table.setRowCount(total_rows)

        for i, sp in enumerate(folders):
            name = os.path.basename(sp.rstrip("/\\"))
            # 复选
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.Unchecked)
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            self.table.setItem(i, 0, chk)
            # 服务器名
            nm = QTableWidgetItem(name)
            nm.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            nm.setToolTip(sp)
            self.table.setItem(i, 1, nm)
            # 本地匹配下拉
            combo = QComboBox()
            combo.addItem("（无本地项目文件夹）", "")
            cands = self._local_candidates(name, local_pool)
            for d, p, sc in cands:
                combo.addItem(f"{d}  ({sc}%)  — {p}", p)
            if cands:
                combo.setCurrentIndex(1)  # 默认选最佳
            self.table.setCellWidget(i, 2, combo)
            self._local_choices[sp] = combo.itemData(combo.currentIndex()) or ""
            combo.currentIndexChanged.connect(
                lambda idx, c=combo, s=sp: self._local_choices.__setitem__(s, c.itemData(idx) or "")
            )

        # 本地独有行
        for j, (d, lp) in enumerate(unmatched_local):
            row = len(folders) + j
            self._local_only_rows.add(row)
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.Unchecked)
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            self.table.setItem(row, 0, chk)
            nm = QTableWidgetItem(f"{d}（仅本地）")
            nm.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            nm.setToolTip(lp)
            self.table.setItem(row, 1, nm)
            # 本地目录下拉（仅本地本身）
            combo = QComboBox()
            combo.addItem(d, lp)
            self.table.setCellWidget(row, 2, combo)
            self._local_choices[lp] = lp

    def _collect_server_folders(self) -> list[str]:
        folders: list[str] = []
        for r in config_manager.nas_roots:
            if not r:
                continue
            try:
                for c in nas_indexer.indexer.list_children(r):
                    if c.get("is_dir"):
                        folders.append(c["path"])
            except Exception:  # noqa: BLE001
                continue
        return folders

    def _gather_local(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for lr in config_manager.local_roots:
            if os.path.isdir(lr):
                try:
                    for d in os.listdir(lr):
                        p = os.path.join(lr, d)
                        if os.path.isdir(p):
                            out.append((d, p))
                except OSError:
                    continue
        return out

    @staticmethod
    def _local_candidates(name: str, local_pool: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
        cands = []
        # 至少 50% 底限（与 matcher.match_project 一致），并应用用户设置的阈值
        cutoff = max(50, config_manager.match_threshold)
        for d, p in local_pool:
            sc, _ = matcher.score_pair(name, d)
            if sc >= cutoff:
                cands.append((d, p, sc))
        cands.sort(key=lambda x: x[2], reverse=True)
        return cands[:5]

    # --------------------------- 交互 ---------------------------
    def _apply_filter(self):
        text = self.search.text().strip().lower()
        for i in range(self.table.rowCount()):
            nm = self.table.item(i, 1)
            hidden = bool(text) and text not in (nm.text().lower() if nm else "")
            self.table.setRowHidden(i, hidden)

    def get_results(self) -> list[tuple[str, str]]:
        results = []
        for i in range(self.table.rowCount()):
            chk = self.table.item(i, 0)
            if chk and chk.checkState() == Qt.Checked:
                if i in self._local_only_rows:
                    # 本地独有：server_path 为空，仅用本地路径
                    lp = self.table.item(i, 1).toolTip()
                    results.append(("", lp))
                else:
                    sp = self.table.item(i, 1).toolTip()
                    results.append((sp, self._local_choices.get(sp, "")))
        return results
