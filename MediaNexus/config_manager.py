# -*- coding: utf-8 -*-
"""
MediaNexus - 配置管理模块
负责加载 / 保存用户配置（JSON 格式），包含：
  - 本地总项目根目录
  - N 个 NAS 服务器素材根目录
  - 每个本地项目的匹配结果（候选 / 已确认路径 / 最后同步时间）
  - 全局设置（匹配阈值、忽略关键词、排除列表等）

所有修改即时落盘，保证「用户操作必须即时保存」的约束。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .constants import (
    CONFIG_PATH,
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_MATCH_THRESHOLD,
)
from .models import Project


# ── 配置 Schema 版本化迁移 ──
# 每个迁移函数接收 raw dict，原地修改并返回。
# MIGRATIONS[N] 将数据从 version N 升级到 N+1。

CURRENT_SCHEMA_VERSION = 2


def _migrate_0_to_1(data: dict) -> None:
    """v0 → v1: local_root(单字符串) → local_roots(列表)"""
    if "local_roots" not in data:
        lr = data.get("local_root", "")
        data["local_roots"] = [lr] if lr else []
    data.pop("local_root", None)


def _migrate_1_to_2(data: dict) -> None:
    """v1 → v2: 确保 settings 中存在 project_mode 和 ffmpeg 字段"""
    settings = data.setdefault("settings", {})
    settings.setdefault("project_mode", "both")
    settings.setdefault("ffmpeg_manual_dir", "")
    settings.setdefault("ffmpeg_download_url", "")
    settings.setdefault("auto_refresh_enabled", False)
    settings.setdefault("auto_refresh_interval", 60)


MIGRATIONS: dict[int, callable] = {
    0: _migrate_0_to_1,
    1: _migrate_1_to_2,
}


def _run_migrations(data: dict) -> dict:
    """按版本链逐步迁移到 CURRENT_SCHEMA_VERSION。"""
    version = data.get("version", 0)
    while version < CURRENT_SCHEMA_VERSION:
        migrate_fn = MIGRATIONS.get(version)
        if migrate_fn is None:
            break  # 无迁移路径，停止（避免死循环）
        migrate_fn(data)
        version += 1
        data["version"] = version
    return data


class ConfigManager:
    """线程安全的配置读写器（单例风格，全局共享一份配置）。"""

    def __init__(self, path: Path = CONFIG_PATH):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = self._default()
        self.load()

    # --------------------------- 默认结构 ---------------------------
    @staticmethod
    def _default() -> dict[str, Any]:
        return {
            "version": CURRENT_SCHEMA_VERSION,
            "onboarding_done": False,  # 首次启动引导是否已完成
            "local_roots": [],        # list[str]  本地项目根目录（可多个，与 nas_roots 对称）
            "nas_roots": [],          # list[str]  UNC 或盘符
            "projects": [],           # 见文件头 Data Structure Example
            "settings": {
                "match_threshold": DEFAULT_MATCH_THRESHOLD,
                "ignore_patterns": list(DEFAULT_IGNORE_PATTERNS),
                "excluded": {},       # {项目名: [被排除的 NAS 路径,...]}
                "auto_refresh_enabled": False,    # 心跳自动刷新服务器
                "auto_refresh_interval": 60,     # 心跳间隔（秒）
                "project_mode": "both",  # "both" | "local_only" | "server_only"
                # FFmpeg 组件：用户可手动指定目录或自定义下载地址
                "ffmpeg_manual_dir": "",        # 用户手动指定的 FFmpeg 目录
                "ffmpeg_download_url": "",      # 自定义下载地址；为空则用内置默认
            },
            "qc_presets": {          # 检测预设（QC 子系统唯一来源，VideoQC 直接读写此处）
                "default": {
                    "name": "默认预设",
                    "description": "VideoQC Pro 默认检测参数",
                    "thresholds": {
                        "black_frame": {"mean_pixel_threshold": 3, "min_duration": 1},
                        "black_border": {"cliff_gradient_min": 25, "border_mean_max": 6, "border_std_max": 6, "contrast_ratio_min": 4.0, "min_border_px": 3, "mode_ratio_min": 0.90},
                        "silence": {"rms_threshold": 0.005, "min_duration_ignore": 0.5, "min_duration_warn": 2.0, "min_duration_error": 5.0},
                    },
                },
            },
            "qc_active_preset": "default",
            "qc_settings": {},       # QC 子系统其他设置（theme/language/last_output_dir/...）
            "indexed_at": "",        # 最近一次索引时间 ISO
        }

    # --------------------------- 读写 ---------------------------
    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                    # 运行版本迁移链（v0→v1→v2→...→current）
                    raw = _run_migrations(raw)
                    # 合并默认键，防止旧配置缺字段
                    merged = self._default()
                    merged.update(raw)
                    merged.setdefault("settings", {})
                    for k, v in self._default()["settings"].items():
                        merged["settings"].setdefault(k, v)
                    self._data = merged
                except (json.JSONDecodeError, OSError):
                    # 损坏则回退默认，但不覆盖文件以免丢失
                    pass

    def save(self) -> bool:
        """即时保存。返回是否成功（失败用于 UI 提示）。"""
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(self._data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                # 原子替换，避免写一半断电导致配置损坏
                tmp.replace(self._path)
                return True
            except OSError:
                return False

    # --------------------------- 属性访问 ---------------------------
    @property
    def data(self) -> dict[str, Any]:
        with self._lock:
            return self._data

    @property
    def local_roots(self) -> list[str]:
        return list(self._data.get("local_roots", []))

    @local_roots.setter
    def local_roots(self, value: list[str]) -> None:
        with self._lock:
            self._data["local_roots"] = [str(v) for v in (value or [])]
        self.save()

    @property
    def nas_roots(self) -> list[str]:
        return list(self._data.get("nas_roots", []))

    @nas_roots.setter
    def nas_roots(self, value: list[str]) -> None:
        with self._lock:
            self._data["nas_roots"] = list(value)
        self.save()

    @property
    def projects(self) -> list[dict]:
        """返回项目列表的浅拷贝——调用方迭代安全（内部可能被其他线程修改）。"""
        with self._lock:
            return list(self._data.get("projects", []))

    def _projects_list(self) -> list[dict]:
        """返回内部 projects 列表的直接引用（仅内部方法使用，外部用 .projects）。"""
        return self._data.setdefault("projects", [])

    @property
    def settings(self) -> dict[str, Any]:
        return self._data.setdefault("settings", {})

    @property
    def match_threshold(self) -> int:
        return int(self.settings.get("match_threshold", DEFAULT_MATCH_THRESHOLD))

    @match_threshold.setter
    def match_threshold(self, value: int) -> None:
        with self._lock:
            self.settings["match_threshold"] = int(value)
        self.save()

    @property
    def ignore_patterns(self) -> list[str]:
        return list(self.settings.get("ignore_patterns", []))

    @ignore_patterns.setter
    def ignore_patterns(self, value: list[str]) -> None:
        with self._lock:
            self.settings["ignore_patterns"] = list(value)
        self.save()

    # --------------------------- 自动刷新（心跳） ---------------------------
    @property
    def auto_refresh_enabled(self) -> bool:
        return bool(self.settings.get("auto_refresh_enabled", False))

    @auto_refresh_enabled.setter
    def auto_refresh_enabled(self, value: bool) -> None:
        with self._lock:
            self.settings["auto_refresh_enabled"] = bool(value)
        self.save()

    @property
    def auto_refresh_interval(self) -> int:
        return int(self.settings.get("auto_refresh_interval", 60))

    @auto_refresh_interval.setter
    def auto_refresh_interval(self, value: int) -> None:
        with self._lock:
            self.settings["auto_refresh_interval"] = int(value)
        self.save()

    # --------------------------- 项目运行模式 ---------------------------
    @property
    def project_mode(self) -> str:
        return self.settings.get("project_mode", "both")

    @project_mode.setter
    def project_mode(self, value: str) -> None:
        with self._lock:
            self.settings["project_mode"] = value
        self.save()

    # --------------------------- 首次启动引导 ---------------------------
    @property
    def onboarding_done(self) -> bool:
        return bool(self._data.get("onboarding_done", False))

    @onboarding_done.setter
    def onboarding_done(self, value: bool) -> None:
        with self._lock:
            self._data["onboarding_done"] = bool(value)
        self.save()

    # --------------------------- FFmpeg 组件管理 ---------------------------
    @property
    def ffmpeg_manual_dir(self) -> str:
        return str(self.settings.get("ffmpeg_manual_dir", ""))

    @ffmpeg_manual_dir.setter
    def ffmpeg_manual_dir(self, value: str) -> None:
        with self._lock:
            self.settings["ffmpeg_manual_dir"] = str(value)
        self.save()

    @property
    def ffmpeg_download_url(self) -> str:
        return str(self.settings.get("ffmpeg_download_url", ""))

    @ffmpeg_download_url.setter
    def ffmpeg_download_url(self, value: str) -> None:
        with self._lock:
            self.settings["ffmpeg_download_url"] = str(value)
        self.save()

    # --------------------------- 检测预设 ---------------------------
    @property
    def qc_presets(self) -> dict:
        return self._data.get("qc_presets", {})

    @qc_presets.setter
    def qc_presets(self, value: dict) -> None:
        with self._lock:
            self._data["qc_presets"] = value
        self.save()

    @property
    def qc_active_preset(self) -> str:
        return self._data.get("qc_active_preset", "default")

    @qc_active_preset.setter
    def qc_active_preset(self, value: str) -> None:
        with self._lock:
            self._data["qc_active_preset"] = value
        self.save()

    # --------------------------- 项目 CRUD ---------------------------
    def get_project(self, local_name: str) -> dict | None:
        for p in self._projects_list():
            if p.get("local_name") == local_name:
                return p
        return None

    def upsert_project(self, project: dict) -> None:
        """新增或更新一个项目记录，并即时落盘。

        写入前通过 Project 模型校验字段合法性（local_name 非空、status 合法），
        不合法时抛出 ValueError，避免脏数据落盘。
        """
        # 边界校验：利用 dataclass 的 __post_init__ 做约束检查
        Project.from_dict(project)
        with self._lock:
            name = project.get("local_name")
            plist = self._projects_list()
            for i, p in enumerate(plist):
                if p.get("local_name") == name:
                    plist[i] = project
                    break
            else:
                plist.append(project)
        self.save()

    def remove_project(self, local_name: str) -> bool:
        """删除一个项目记录（含其排除列表），即时落盘。返回是否找到并删除。"""
        with self._lock:
            plist = self._projects_list()
            for i, p in enumerate(plist):
                if p.get("local_name") == local_name:
                    plist.pop(i)
                    excluded = self.settings.get("excluded", {})
                    excluded.pop(local_name, None)
                    break
            else:
                return False
        return self.save()

    def cleanup_stale_projects(self) -> int:
        """清理「服务器目录已失效」的项目记录（新模型下项目以服务器目录为锚点）。

        仅当 confirmed_nas_path 为本地型路径且已不存在时才清理；UNC 路径离线
        时不轻易剔除，避免误删（无本地文件夹的项目应保留，见需求5）。
        返回清理数量。
        """
        import os
        removed = 0
        with self._lock:
            kept = []
            plist = self._projects_list()
            for p in plist:
                sp = p.get("confirmed_nas_path", "")
                drop = False
                if sp:
                    is_unc = sp.startswith("\\\\") or sp.startswith("//")
                    if (not is_unc) and not os.path.isdir(sp):
                        drop = True
                if drop:
                    removed += 1
                    excluded = self.settings.get("excluded", {})
                    excluded.pop(p.get("local_name", ""), None)
                else:
                    kept.append(p)
            self._data["projects"] = kept
        if removed:
            self.save()
        return removed

    def set_confirmed_nas(self, local_name: str, nas_path: str) -> None:
        """确认某服务器路径绑定到项目，记录同步时间。整个方法加锁防止竞态。"""
        with self._lock:
            proj = self.get_project(local_name)
            if proj is None:
                proj = {
                    "local_name": local_name,
                    "local_path": "",
                    "nas_candidates": [],
                    "confirmed_nas_path": "",
                    "last_sync": "",
                }
                self._projects_list().append(proj)
            proj["confirmed_nas_path"] = nas_path
            from datetime import datetime
            proj["last_sync"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    def set_indexed_at(self, iso: str) -> None:
        with self._lock:
            self._data["indexed_at"] = iso
        self.save()


# 全局单例，供各模块直接引用，避免重复加载。
config_manager = ConfigManager()
