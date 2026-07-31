"""
FFmpeg 路径管理器（内置完整版 + 按需下载兜底）
================================================================
解析优先级（找到即止）：
  1. 系统 PATH 中的 ffmpeg / ffprobe（用户已自行安装，优先级最高）
  2. 用户在「设置 → 组件」中手动指定的目录（覆盖内置）
  3. 安装包内置的 resources/ffmpeg（完整版静态构建，开箱即用、离线可用）
  4. 运行时下载缓存目录：%APPDATA%/MediaNexus/ffmpeg/bin（兜底）

分发策略：
  - 安装包随附 gyan.dev 的「完整版静态构建」（ffmpeg.exe + ffprobe.exe + ffplay.exe，
    全部编解码器/滤镜，静态链接无 DLL 依赖），覆盖现有质检功能及后续扩展的全部需求。
  - 若内置版本缺失，可手动点击下载到缓存目录（DEFAULT_DOWNLOAD_URL）。
打包前请运行：python scripts/fetch_ffmpeg.py
"""
from __future__ import annotations

import os
import sys
import platform
import shutil
import subprocess
import logging
import zipfile
import tempfile
import urllib.request

logger = logging.getLogger("VideoQC.FFmpegManager")

# 默认下载地址（兜底用；内置完整版已覆盖全部场景）。
# 使用 gyan.dev 的 GitHub 镜像（CDN 稳定），release 完整版静态构建。
# 可在设置中替换为国内可达镜像。
DEFAULT_DOWNLOAD_URL = "https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-full_build.zip"


class FFmpegManager:
    """FFmpeg 二进制文件管理器（单例）。"""

    _instance = None
    _ffmpeg_path = None
    _ffprobe_path = None
    _available = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._resolve()
        return cls._instance

    # --------------------------- 路径计算 ---------------------------
    def _app_data_dir(self) -> str:
        """跨平台的应用数据目录（与 CONFIG_DIR=%APPDATA%/MediaNexus 对齐）。"""
        base = os.environ.get("APPDATA")
        if not base:
            base = os.path.expanduser("~/.config")
        d = os.path.join(base, "MediaNexus")
        os.makedirs(d, exist_ok=True)
        return d

    def _cache_dir(self) -> str:
        """FFmpeg 下载缓存根目录。"""
        return os.path.join(self._app_data_dir(), "ffmpeg")

    def _get_base_dir(self):
        """程序根目录（兼容开发环境与打包环境）。"""
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                return sys._MEIPASS
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _exe(self, name: str) -> str:
        return f"{name}.exe" if platform.system().lower() == "windows" else name

    # --------------------------- 解析 ---------------------------
    def _which(self, name: str):
        """在系统 PATH 中查找可执行文件。"""
        exe = self._exe(name)
        found = shutil.which(exe)
        return found

    def _manual_dir(self) -> str:
        """读取用户手动指定的目录（来自配置）。"""
        try:
            from MediaNexus.config_manager import config_manager
            return (config_manager.settings.get("ffmpeg_manual_dir") or "").strip()
        except Exception:
            return ""

    def _download_url(self) -> str:
        """读取可配置的下载地址。"""
        try:
            from MediaNexus.config_manager import config_manager
            url = (config_manager.settings.get("ffmpeg_download_url") or "").strip()
            if url:
                return url
        except Exception:
            pass
        return DEFAULT_DOWNLOAD_URL

    def _resolve(self):
        """按优先级确定 ffmpeg / ffprobe 路径。"""
        candidates = []

        # 1. 系统 PATH（用户已自行安装，优先级最高）
        p = self._which("ffmpeg")
        if p:
            candidates.append(os.path.dirname(p))

        # 2. 用户手动指定目录（覆盖内置）
        md = self._manual_dir()
        if md:
            candidates.append(md)

        # 3. 安装包内置完整版构建（开箱即用、离线可用，默认来源）
        bundled = os.path.join(self._get_base_dir(), "resources", "ffmpeg")
        candidates.append(bundled)

        # 4. 运行时下载缓存（兜底：内置缺失或用户需要完整版时）
        candidates.append(os.path.join(self._cache_dir(), "bin"))

        ffmpeg_exe = self._exe("ffmpeg")
        ffprobe_exe = self._exe("ffprobe")
        self._ffmpeg_path = None
        self._ffprobe_path = None
        for d in candidates:
            fp = os.path.join(d, ffmpeg_exe)
            pp = os.path.join(d, ffprobe_exe)
            if os.path.isfile(fp) and os.path.isfile(pp):
                self._ffmpeg_path = fp
                self._ffprobe_path = pp
                break

        self._available = bool(self._ffmpeg_path)
        if self._available:
            logger.info(f"FFmpeg 路径: {self._ffmpeg_path}")
            logger.info(f"FFprobe 路径: {self._ffprobe_path}")
        else:
            logger.warning("FFmpeg 未找到（PATH / 缓存 / 手动 / 内置 均缺失）")
            # 保留一个"预期路径"用于错误提示
            self._ffmpeg_path = os.path.join(self._cache_dir(), "bin", ffmpeg_exe)
            self._ffprobe_path = os.path.join(self._cache_dir(), "bin", ffprobe_exe)

    # --------------------------- 公开属性 ---------------------------
    @property
    def ffmpeg_path(self):
        return self._ffmpeg_path

    @property
    def ffprobe_path(self):
        return self._ffprobe_path

    @property
    def is_available(self):
        return self._available

    def get_ffmpeg_path(self):
        return self._ffmpeg_path

    def get_ffprobe_path(self):
        return self._ffprobe_path

    def verify(self):
        """验证 FFmpeg 是否可用。"""
        if not self._available:
            return False, "FFmpeg 二进制文件未找到"
        try:
            kw = dict(capture_output=True, timeout=10, encoding="utf-8", errors="replace")
            if platform.system() == "Windows":
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run([self._ffmpeg_path, "-version"], **kw)
            if result.returncode == 0:
                stdout = result.stdout or ""
                version_line = stdout.split("\n")[0] if stdout else "未知版本"
                return True, f"FFmpeg 可用: {version_line}"
            return False, f"FFmpeg 运行异常: {result.stderr or ''}"
        except FileNotFoundError:
            return False, f"找不到 FFmpeg: {self._ffmpeg_path}"
        except Exception as e:
            return False, f"FFmpeg 验证失败: {str(e)}"

    # --------------------------- 手动指定 ---------------------------
    def set_manual_dir(self, path: str) -> bool:
        """用户手动指定包含 ffmpeg/ffprobe 的目录。返回是否生效。"""
        path = (path or "").strip()
        if not path:
            return False
        exe = self._exe("ffmpeg")
        prb = self._exe("ffprobe")
        if not (os.path.isfile(os.path.join(path, exe)) and os.path.isfile(os.path.join(path, prb))):
            return False
        try:
            from MediaNexus.config_manager import config_manager
            config_manager.settings["ffmpeg_manual_dir"] = path
            config_manager.save()
        except Exception:
            pass
        self._resolve()
        return self._available

    # --------------------------- 按需下载 ---------------------------
    def ensure_ffmpeg(self, progress_cb=None, force: bool = False):
        """
        确保 FFmpeg 可用；若不可用则下载解压到缓存目录。
        参数 progress_cb(fraction:float, status:str) -> bool：返回 False 可中断。
        返回 (ok:bool, message:str)。
        """
        if self._available and not force:
            return True, "FFmpeg 已就绪"
        if progress_cb and not progress_cb(0.0, "准备下载 FFmpeg…"):
            return False, "已取消"

        url = self._download_url()
        if not url:
            return False, "未配置下载地址，请在「设置 → 组件」中指定 FFmpeg 文件夹或下载链接"

        bin_dir = os.path.join(self._cache_dir(), "bin")
        os.makedirs(bin_dir, exist_ok=True)

        try:
            tmp_dir = tempfile.mkdtemp(prefix="medianexus_ff_")
            zip_path = os.path.join(tmp_dir, "ffmpeg.zip")
            if not self._download_file(url, zip_path, progress_cb):
                return False, "下载已取消"
            if progress_cb and not progress_cb(0.9, "解压 FFmpeg…"):
                return False, "已取消"
            self._extract_ffmpeg(zip_path, bin_dir)
        except Exception as e:
            logger.exception("FFmpeg 下载/解压失败")
            return False, f"FFmpeg 获取失败: {str(e)}"
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        self._resolve()
        if self._available:
            return True, "FFmpeg 已下载并就绪"
        return False, "解压后仍未找到 ffmpeg/ffprobe，请改用「设置 → 组件」手动指定"

    def _download_file(self, url: str, dest: str, progress_cb=None) -> bool:
        """下载文件，分块写入并通过 progress_cb 报告进度（0~0.85）。"""

        def _reporthook(block_num, block_size, total_size):
            if progress_cb is None or not total_size:
                return
            frac = min(0.85, block_num * block_size / total_size)
            if not progress_cb(frac, f"下载 FFmpeg… {int(frac * 100)}%"):
                raise _CancelDownload()

        try:
            urllib.request.urlretrieve(url, dest, _reporthook)
        except _CancelDownload:
            return False
        except Exception:
            logger.exception("下载失败")
            raise
        return True

    def _extract_ffmpeg(self, zip_path: str, out_bin_dir: str):
        """从 zip 中找出 ffmpeg/ffprobe 可执行文件并复制到 out_bin_dir。"""
        ffmpeg_exe = self._exe("ffmpeg")
        ffprobe_exe = self._exe("ffprobe")
        found = {}
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                base = os.path.basename(name)
                if base in (ffmpeg_exe, ffprobe_exe):
                    with zf.open(name) as src, open(os.path.join(out_bin_dir, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    found[base] = True
        if ffmpeg_exe not in found or ffprobe_exe not in found:
            raise FileNotFoundError(f"压缩包内未包含 {ffmpeg_exe} / {ffprobe_exe}")


class _CancelDownload(Exception):
    """内部异常：用于中断 urllib 下载。"""
    pass
