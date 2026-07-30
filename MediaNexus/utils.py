# -*- coding: utf-8 -*-
"""
MediaNexus - 通用工具函数
包含：路径安全处理、人类可读大小、重试装饰器、文件名合法性校验等。
"""
from __future__ import annotations

import functools
import os
import sys
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def human_readable_size(num_bytes: int) -> str:
    """将字节数转换为人类可读字符串（中文单位）。"""
    if num_bytes is None or num_bytes < 0:
        return "-"
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if size < 1024.0 or unit == "PB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def normalize_path(path: str) -> str:
    """
    规范化路径：统一为正斜杠、展开用户目录、解析父引用。
    对 UNC 路径（\\server\\share）保留原样（normpath 不会破坏 UNC）。
    """
    if not path:
        return ""
    p = os.path.expanduser(path)
    # ntpath.normpath 能正确处理 Windows / UNC 路径
    p = os.path.normpath(p)
    return p


def is_unc_path(path: str) -> bool:
    """判断是否为 UNC 网络路径（\\server\\share）。"""
    return bool(path) and (path.startswith("\\\\") or path.startswith("//"))


def safe_filename(name: str) -> str:
    """生成一个安全的纯 ASCII 文件名片段，用于缓存/日志等（不影响真实路径）。"""
    import re
    keep = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    return keep[:60]


def retry(
    times: int = 3,
    interval: float = 1.0,
    exceptions: tuple = (OSError, PermissionError),
    on_fail: Callable[[Exception, int], None] | None = None,
):
    """
    简单同步重试装饰器：被装饰函数在抛出指定异常时自动重试。
    :param on_fail: 每次失败后的回调 (exc, attempt)，可用于 UI 提示。
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # noqa: B902
                    last_exc = exc
                    if on_fail:
                        on_fail(exc, attempt)
                    if attempt < times:
                        time.sleep(interval)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


def list_dir_safe(path: str, ignore_patterns: list[str] | None = None) -> list[dict]:
    """
    安全列出目录内容（同步，供后台线程调用）。
    返回列表，每个元素为 dict: {name, path, is_dir, size, mtime}
    任何异常（权限/断连）向上抛出，由调用方处理重试/提示。
    已过滤 ignore_patterns（大小写不敏感）匹配的项。
    """
    from .constants import DEFAULT_IGNORE_PATTERNS

    patterns = [p.lower() for p in (ignore_patterns or DEFAULT_IGNORE_PATTERNS)]
    entries: list[dict] = []
    with os.scandir(path) as it:
        for entry in it:
            try:
                lower_name = entry.name.lower()
                if any(pat in lower_name for pat in patterns):
                    continue
                is_dir = entry.is_dir()
                stat = entry.stat()
                entries.append(
                    {
                        "name": entry.name,
                        "path": entry.path,
                        "is_dir": is_dir,
                        "size": stat.st_size if not is_dir else 0,
                        "mtime": stat.st_mtime,
                    }
                )
            except (PermissionError, OSError):
                # 单个文件/目录无权限不影响整体，跳过
                continue
    # 文件夹在前，文件在后；各自按名称排序
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries


def open_file(path: str) -> bool:
    """用系统默认程序直接打开文件（如 mp4 播放、prproj 进 Premiere）。"""
    try:
        os.startfile(os.path.normpath(path))  # noqa: S606
        return True
    except Exception:  # noqa: BLE001
        return False


def open_in_explorer(path: str) -> bool:
    """
    在 Windows 资源管理器中打开文件或文件夹。
    文件夹直接打开；文件则用 explorer /select 定位并选中（仅打开一次）。
    """
    try:
        if os.path.isfile(path):
            # 只用 explorer /select 一次定位文件，不再额外 startfile 父目录
            import subprocess

            subprocess.Popen(
                ["explorer", "/select,", os.path.normpath(path)]
            )
        else:
            os.startfile(os.path.normpath(path))  # noqa: S606
        return True
    except Exception:  # noqa: BLE001
        return False


def copy_path_to_clipboard(text: str) -> bool:
    """将文本写入系统剪贴板（Windows 平台）。"""
    try:
        import win32clipboard  # type: ignore

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        win32clipboard.CloseClipboard()
        return True
    except Exception:  # noqa: BLE001
        try:
            import subprocess

            subprocess.run(
                ["powershell", "-command", f'Set-Clipboard -Value "{text}"'],
                check=False,
                capture_output=True,
            )
            return True
        except Exception:  # noqa: BLE001
            return False


def resource_path(rel: str) -> str:
    """获取资源绝对路径。兼容源码运行与 PyInstaller 打包后运行。

    PyInstaller 把数据文件解到临时目录 sys._MEIPASS；源码运行时
    以项目根目录（utils.py 的上两级）为基准。
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", rel)


def check_overwrite_conflicts(parent, src_paths: list[str], dst_dir: str) -> bool:
    """复制/移动前检查目标目录是否有同名文件，有则弹窗询问是否覆盖。

    :param parent: 父 QWidget 用于作为弹窗的 parent
    :param src_paths: 源文件路径列表
    :param dst_dir: 目标目录
    :return: True=继续（覆盖或无冲突），False=取消
    """
    from PySide6.QtWidgets import QMessageBox
    conflicts = []
    for src in src_paths:
        name = os.path.basename(src.rstrip("/\\"))
        if name and os.path.exists(os.path.join(dst_dir, name)):
            conflicts.append(name)
    if not conflicts:
        return True
    preview = "\n".join(conflicts[:10])
    if len(conflicts) > 10:
        preview += f"\n…等共 {len(conflicts)} 个"
    reply = QMessageBox.question(
        parent, "存在同名文件",
        f"以下文件在目标目录已存在，是否覆盖？\n\n{preview}",
        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes,
    )
    return reply == QMessageBox.Yes
