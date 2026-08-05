"""
统一存储管理器
确保程序所有衍生文件（日志、缓存、导出）按规范目录结构存放，
杜绝文件散落。提供缓存大小查询和一键清除功能。
"""

import os
import sys
import shutil
import logging

logger = logging.getLogger("MediaNexus.QC.Storage")


class StorageManager:
    """统一存储管理器（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._base_dir = self._resolve_base_dir()
        self._ensure_dirs()
        logger.info(f"存储根目录: {self._base_dir}")

    # ---- 路径解析 ----

    def _resolve_base_dir(self):
        """获取程序根目录"""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @property
    def data_dir(self):
        return os.path.join(self._base_dir, "data")

    @property
    def logs_dir(self):
        return os.path.join(self.data_dir, "logs")

    @property
    def cache_dir(self):
        return os.path.join(self.data_dir, "cache")

    @property
    def exports_dir(self):
        return os.path.join(self.data_dir, "exports")

    @property
    def config_path(self):
        return os.path.join(self._base_dir, "config.json")

    # ---- 目录初始化 ----

    def _ensure_dirs(self):
        """确保所有必要的目录存在"""
        for d in [self.data_dir, self.logs_dir, self.cache_dir,
                   self.exports_dir]:
            os.makedirs(d, exist_ok=True)

    # ---- 便捷路径 ----

    def get_cache_path(self, *subpath, ensure_dir=True):
        """
        获取缓存目录下的文件路径，自动创建父目录
        示例: get_cache_path("audio", "extracted.wav")
        """
        path = os.path.join(self.cache_dir, *subpath)
        if ensure_dir:
            parent = os.path.dirname(path)
            os.makedirs(parent, exist_ok=True)
        return path

    # ---- 全项目缓存管理 ----

    def get_all_cache_info(self):
        """汇总全项目所有可清理缓存的大小信息。

        Returns:
            dict: {
                "total_mb": float,
                "items": [
                    {"id": str, "name": str, "path": str, "size_mb": float, "file_count": int},
                    …
                ]
            }
        """
        items = []

        # 1. QC 检测结果缓存（%APPDATA%/MediaNexus/qc_cache.db）
        qc_mb, qc_count = 0.0, 0
        qc_path = self._get_qc_cache_path()
        if os.path.isfile(qc_path):
            qc_mb = os.path.getsize(qc_path) / (1024 * 1024)
            qc_count = 1
        items.append({"id": "qc_cache", "name": "QC 检测结果缓存", "path": qc_path,
                       "size_mb": round(qc_mb, 2), "file_count": qc_count})

        # 2. 音频提取缓存
        audio_mb, audio_count = 0.0, 0
        audio_dir = self._get_audio_cache_dir()
        if os.path.isdir(audio_dir):
            audio_mb, audio_count = self._scan_dir(audio_dir)
        items.append({"id": "audio_cache", "name": "音频提取缓存", "path": audio_dir,
                       "size_mb": audio_mb, "file_count": audio_count})

        # 3. FFmpeg 下载缓存
        ff_mb, ff_count = 0.0, 0
        ff_dir = self._get_ffmpeg_cache_dir()
        if os.path.isdir(ff_dir):
            ff_mb, ff_count = self._scan_dir(ff_dir)
        items.append({"id": "ffmpeg_cache", "name": "FFmpeg 下载缓存", "path": ff_dir,
                       "size_mb": ff_mb, "file_count": ff_count})

        # 4. 崩溃日志
        cr_mb, cr_count = 0.0, 0
        cr_path = self._get_crash_log_path()
        if os.path.isfile(cr_path):
            cr_mb = os.path.getsize(cr_path) / (1024 * 1024)
            cr_count = 1
        items.append({"id": "crash_log", "name": "崩溃日志", "path": cr_path,
                       "size_mb": round(cr_mb, 2), "file_count": cr_count})

        total = sum(it["size_mb"] for it in items)
        return {"total_mb": round(total, 2), "items": items}

    def clear_all_caches(self, targets: set[str]):
        """按用户选择清除缓存。

        Args:
            targets: 要清除的缓存 ID 集合（如 {"qc_cache","audio_cache","ffmpeg_cache"}）

        Returns:
            dict: {"freed_mb": float, "errors": list[str]}
        """
        result = {"freed_mb": 0.0, "errors": []}

        for tid in targets:
            try:
                if tid == "qc_cache":
                    r = self._clear_file(self._get_qc_cache_path())
                elif tid == "audio_cache":
                    r = self._clear_dir(self._get_audio_cache_dir())
                elif tid == "ffmpeg_cache":
                    r = self._clear_dir(self._get_ffmpeg_cache_dir())
                elif tid == "crash_log":
                    r = self._clear_file(self._get_crash_log_path())
                else:
                    continue
                result["freed_mb"] += r["freed_mb"]
                result["errors"].extend(r.get("errors", []))
            except Exception as e:
                result["errors"].append(f"{tid}: {e}")
        result["freed_mb"] = round(result["freed_mb"], 2)
        return result

    # ---- 内部辅助 ----

    def _scan_dir(self, path: str) -> tuple[float, int]:
        """扫描目录：返回 (总MB, 文件数)。"""
        total, count = 0, 0
        if not os.path.isdir(path):
            return 0.0, 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                        count += 1
                    except OSError:
                        pass
        except OSError:
            pass
        return round(total / (1024 * 1024), 2), count

    def _clear_dir(self, path: str) -> dict:
        """清空目录（保留目录本身，删除内容）。"""
        result = {"freed_mb": 0.0, "errors": []}
        if not os.path.isdir(path):
            return result
        for entry in os.listdir(path):
            ep = os.path.join(path, entry)
            try:
                size = self._dir_size(ep) if os.path.isdir(ep) else os.path.getsize(ep)
                if os.path.isfile(ep) or os.path.islink(ep):
                    os.remove(ep)
                else:
                    shutil.rmtree(ep)
                result["freed_mb"] += size / (1024 * 1024)
            except OSError as e:
                result["errors"].append(f"{ep}: {e}")
        result["freed_mb"] = round(result["freed_mb"], 2)
        return result

    def _clear_file(self, path: str) -> dict:
        """删除单个文件。"""
        result = {"freed_mb": 0.0, "errors": []}
        if not os.path.isfile(path):
            return result
        try:
            result["freed_mb"] = os.path.getsize(path) / (1024 * 1024)
            os.remove(path)
        except OSError as e:
            result["errors"].append(f"{path}: {e}")
        result["freed_mb"] = round(result["freed_mb"], 2)
        return result

    def _get_qc_cache_path(self) -> str:
        try:
            from MediaNexus.constants import CONFIG_DIR
            return str(CONFIG_DIR / "qc_cache.db")
        except Exception:
            return os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "qc_cache.db")

    def _get_ffmpeg_cache_dir(self) -> str:
        try:
            from MediaNexus.constants import CONFIG_DIR
            return str(CONFIG_DIR / "ffmpeg")
        except Exception:
            return os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "ffmpeg")

    def _get_audio_cache_dir(self) -> str:
        return os.path.join(self.cache_dir, "audio")

    def _get_crash_log_path(self) -> str:
        try:
            from MediaNexus.constants import CONFIG_DIR
            return str(CONFIG_DIR / "crash.log")
        except Exception:
            return os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "crash.log")

    def _dir_size(self, path):
        """递归计算目录大小"""
        total = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    # ---- 目录清理（迁移辅助）----

    def migrate_legacy_files(self):
        """
        将旧版散落的文件迁移到规范目录中
        从根目录 logs/ → data/logs/
        从根目录 exports/ → data/exports/
        """
        legacy_mappings = {
            "logs": self.logs_dir,
            "exports": self.exports_dir,
        }

        for legacy_dir_name, target_dir in legacy_mappings.items():
            legacy_path = os.path.join(self._base_dir, legacy_dir_name)
            if not os.path.isdir(legacy_path):
                continue
            if os.path.realpath(legacy_path) == os.path.realpath(target_dir):
                continue  # 已经是正确位置

            # 迁移文件
            for entry in os.scandir(legacy_path):
                if entry.is_file():
                    target = os.path.join(target_dir, entry.name)
                    if not os.path.exists(target):
                        try:
                            shutil.move(entry.path, target)
                            logger.info(f"已迁移遗留文件: {entry.path} -> {target}")
                        except OSError as e:
                            logger.warning(f"迁移遗留文件失败: {entry.path} ({e})")

            # 删除空的旧目录
            try:
                if not os.listdir(legacy_path):
                    os.rmdir(legacy_path)
                    logger.info(f"已移除空的旧目录: {legacy_path}")
            except OSError:
                pass
