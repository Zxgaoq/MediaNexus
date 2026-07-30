# -*- coding: utf-8 -*-
"""
MediaNexus - 后台线程 Workers
所有耗时操作（NAS 索引、模糊匹配、目录列举、文件复制）均在子线程执行，
通过信号回传进度与结果，主线程 UI 永不阻塞。
"""
from __future__ import annotations

import os
import shutil
import threading

from PySide6.QtCore import QThread, Signal

from . import indexer as nas_indexer
from .config_manager import config_manager
from .constants import DEFAULT_IGNORE_PATTERNS, STATUS_MATCHED, STATUS_NONE
from . import matcher
from .utils import is_unc_path, list_dir_safe


# ===================================================================
# 1) NAS 索引构建线程
# ===================================================================
class IndexWorker(QThread):
    progress = Signal(int, int, str)   # (dirs, files, current_path)
    finished = Signal(dict)            # stats

    def __init__(self, roots: list[str], pause_event=None, stop_event=None, fast: bool = False):
        super().__init__()
        self.roots = roots
        self.pause_event = pause_event
        self.stop_event = stop_event
        self._fast = fast

    def run(self):
        if self.isInterruptionRequested():
            return
        stats = nas_indexer.indexer.rebuild(
            self.roots,
            progress_cb=lambda d, f, p: self.progress.emit(d, f, p),
            pause_event=self.pause_event,
            stop_event=self.stop_event,
            fast=self._fast,
        )
        if self.isInterruptionRequested():
            return
        # 记录索引时间到配置
        from datetime import datetime

        config_manager.set_indexed_at(datetime.now().isoformat(timespec="seconds"))
        self.finished.emit(stats)


# ===================================================================
# 1b) 增量刷新单个项目子树（供「刷新」按钮 / 心跳自动刷新）
# ===================================================================
class RefreshIndexWorker(QThread):
    finished = Signal(str)   # root 路径
    error = Signal(str, str) # (root, msg)

    def __init__(self, root: str):
        super().__init__()
        self.root = root

    def run(self):
        if self.isInterruptionRequested():
            return
        try:
            nas_indexer.indexer.reindex_subtree(self.root)
            if not self.isInterruptionRequested():
                self.finished.emit(self.root)
        except Exception as e:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.error.emit(self.root, str(e))


# ===================================================================
# 1c) 后台深度扫描已添加的项目（在快速索引后逐项目补全内容）
# ===================================================================
class DeepScanWorker(QThread):
    progress = Signal(int, int, str)   # (done, total, current_path)
    finished = Signal(dict)            # cumulative stats

    def __init__(self, project_roots: list[str]):
        super().__init__()
        self._roots = list(project_roots or [])

    def run(self):
        total = {"dirs": 0, "files": 0, "errors": 0}
        n = len(self._roots)
        for i, root in enumerate(self._roots):
            if self.isInterruptionRequested():
                break
            self.progress.emit(i + 1, n, root)
            res = nas_indexer.indexer.reindex_subtree(root)
            for k in total:
                total[k] += res.get(k, 0)
        self.finished.emit(total)


# ===================================================================
# 2) 智能匹配线程：扫描本地项目目录，对 NAS 索引做模糊匹配
# ===================================================================
class MatchWorker(QThread):
    progress = Signal(int, int, str)   # (current, total, name)
    project_ready = Signal(dict)       # 单个项目匹配结果
    finished = Signal(int)             # 匹配项目总数

    def __init__(
        self,
        local_roots: list[str],
        nas_folders: list[str],
        threshold: int = 80,
        project_names: list[str] | None = None,
    ):
        super().__init__()
        self.local_roots = list(local_roots or [])
        self.nas_folders = nas_folders
        self.threshold = threshold
        self.project_names = set(project_names or [])

    def run(self):
        if self.isInterruptionRequested():
            self.finished.emit(0)
            return
        # 新模型：项目以「服务器文件夹」为锚点（local_name = 服务器路径）。
        # 匹配 = 为每个已添加的项目从多个本地根目录反查对应的本地文件夹。
        projects = config_manager.projects
        explicit_rematch = bool(self.project_names)
        if explicit_rematch:
            projects = [p for p in projects if p.get("local_name") in self.project_names]
        total = len(projects)
        done = 0
        # 项目级候选：只取 NAS 根的直接子文件夹，排除深层子文件夹
        nas_roots = config_manager.nas_roots
        project_candidates: list[str] = []
        if nas_roots:
            project_candidates = [
                f for f in self.nas_folders
                if any(os.path.dirname(f).rstrip("/\\") == r.rstrip("/\\") for r in nas_roots)
            ]
        # 本地路径缓存：一次性扫描所有本地根，建 {basename: path} 表
        self._local_map = self._build_local_map()
        for p in projects:
            if self.isInterruptionRequested():
                break
            server_path = p.get("local_name", "")
            name = p.get("name") or os.path.basename(server_path.rstrip("/\\"))
            local_path = p.get("local_path", "")
            confirmed = p.get("confirmed_nas_path", "")
            stored_candidates = p.get("nas_candidates", [])

            # 匹配缓存：非手动触发且项目已有确认路径 → 跳过匹配，保留已有本地路径不变
            if not explicit_rematch and confirmed and os.path.isdir(confirmed):
                project = dict(p, local_path=local_path, status=STATUS_MATCHED)
                config_manager.upsert_project(project)
                self.project_ready.emit(project)
                done += 1
                self.progress.emit(done, total, name)
                continue

            # 仅在本地路径为空或已失效时重新解析
            if not local_path or not os.path.isdir(local_path):
                local_path = self._resolve_local(name)
            excluded = config_manager.settings.get("excluded", {}).get(server_path, [])
            candidates = matcher.match_project(
                name, project_candidates, threshold=self.threshold,
                top_n=20, excluded=excluded,
            ) if project_candidates else []
            if confirmed:
                candidates = [c for c in candidates if c["path"] != confirmed]
                candidates.insert(0, {
                    "path": confirmed,
                    "name": os.path.basename(confirmed.rstrip("/\\")),
                    "score": 100, "strategy": "exact",
                })
                status = STATUS_MATCHED
            elif candidates:
                status = matcher.decide_status(candidates, self.threshold)
            else:
                status = STATUS_NONE
            project = {
                "local_name": server_path,
                "name": name,
                "local_path": local_path,
                "nas_candidates": candidates,
                "confirmed_nas_path": confirmed,
                "last_sync": p.get("last_sync", ""),
                "status": status,
            }
            config_manager.upsert_project(project)
            self.project_ready.emit(project)

            done += 1
            self.progress.emit(done, total, name)

        self.finished.emit(total)

    def _build_local_map(self) -> dict[str, str]:
        """一次性扫描所有本地根目录，构建 {basename: path} 缓存。"""
        lmap: dict[str, str] = {}
        for lr in self.local_roots:
            if not os.path.isdir(lr):
                continue
            try:
                for d in os.listdir(lr):
                    p = os.path.join(lr, d)
                    if os.path.isdir(p):
                        lmap.setdefault(d.lower(), p)
            except OSError:
                continue
        return lmap

    def _resolve_local(self, name: str) -> str:
        """用缓存的本地映射表快速匹配；不存在时回退到模糊评分。"""
        if not name:
            return ""
        # 精确命中
        hit = self._local_map.get(name.lower())
        if hit and os.path.isdir(hit):
            return hit
        # 模糊后备
        best, best_score = "", -1
        for lr in self.local_roots:
            if not os.path.isdir(lr):
                continue
            try:
                subs = [d for d in os.listdir(lr) if os.path.isdir(os.path.join(lr, d))]
            except OSError:
                continue
            for sub in subs:
                sc, _ = matcher.score_pair(name, sub)
                if sc > best_score:
                    best_score, best = sc, os.path.join(lr, sub)
        cutoff = max(40, int(self.threshold * 0.5))
        return best if best_score >= cutoff else ""


# ===================================================================
# 3) 目录内容列举线程（中栏本地 / 右栏 NAS 共用）
#    优先使用 NAS 索引（快），失败时回退实时扫描（UNC 同样支持）
# ===================================================================
class ListWorker(QThread):
    loaded = Signal(str, list)   # (path, entries)
    error = Signal(str, str)     # (path, error_msg)

    def __init__(self, path: str, ignore_patterns: list[str] | None = None, force_live: bool = False):
        super().__init__()
        self.path = path
        self.ignore_patterns = ignore_patterns or DEFAULT_IGNORE_PATTERNS
        # force_live=True 时跳过 NAS 缓存索引，直接实时扫描服务器（用于「刷新」按钮）
        self.force_live = force_live

    def run(self):
        if self.isInterruptionRequested():
            return
        try:
            entries = self._get_children(self.path)
            if not self.isInterruptionRequested():
                self.loaded.emit(self.path, entries)
        except (OSError, PermissionError) as e:  # noqa: BLE001
            if not self.isInterruptionRequested():
                self.error.emit(self.path, str(e))

    def _get_children(self, path: str) -> list[dict]:
        # NAS 路径默认优先走索引（离线/快速）；force_live 时跳过索引做实时扫描
        if not self.force_live and is_unc_path(path):
            try:
                rows = nas_indexer.indexer.list_children(path)
                if rows:
                    return rows
            except Exception:  # noqa: BLE001
                pass
        # 回退 / 强制：实时扫描（UNC / 本地均可）
        return list_dir_safe(path, self.ignore_patterns)


# ===================================================================
# 4) 文件复制线程（拖拽 NAS -> 本地，触发系统级复制）
# ===================================================================
class CopyWorker(QThread):
    progress = Signal(int, int, str)  # (done, total, current_name)
    finished = Signal(int, int)       # (ok, fail)

    def __init__(self, src_list: list[str], dst_dir: str):
        super().__init__()
        self.src_list = src_list
        self.dst_dir = dst_dir

    def run(self):
        os.makedirs(self.dst_dir, exist_ok=True)
        total = len(self.src_list)
        ok = 0
        fail = 0
        for i, src in enumerate(self.src_list, 1):
            if self.isInterruptionRequested():
                self.finished.emit(ok, fail)
                return
            name = os.path.basename(src.rstrip("/\\"))
            self.progress.emit(i, total, name)
            try:
                dst = os.path.join(self.dst_dir, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
                ok += 1
            except (OSError, shutil.Error) as e:  # noqa: BLE001
                fail += 1
        self.finished.emit(ok, fail)


# ===================================================================
# 4b) 文件移动线程（同栏拖拽到子文件夹，Windows 同盘移动语义）
# ===================================================================
class MoveWorker(QThread):
    progress = Signal(int, int, str)  # (done, total, current_name)
    finished = Signal(int, int)       # (ok, fail)

    def __init__(self, src_list: list[str], dst_dir: str):
        super().__init__()
        self.src_list = src_list
        self.dst_dir = dst_dir

    def run(self):
        os.makedirs(self.dst_dir, exist_ok=True)
        total = len(self.src_list)
        ok = 0
        fail = 0
        for i, src in enumerate(self.src_list, 1):
            if self.isInterruptionRequested():
                self.finished.emit(ok, fail)
                return
            name = os.path.basename(src.rstrip("/\\"))
            self.progress.emit(i, total, name)
            try:
                dst = os.path.join(self.dst_dir, name)
                # 源和目标相同则跳过
                if os.path.normpath(src) == os.path.normpath(dst):
                    ok += 1
                    continue
                shutil.move(src, dst)
                ok += 1
            except (OSError, shutil.Error) as e:  # noqa: BLE001
                fail += 1
        self.finished.emit(ok, fail)


# 共享的暂停 / 中止事件（供索引任务使用）
def make_flags():
    return threading.Event(), threading.Event()  # (pause, stop)
