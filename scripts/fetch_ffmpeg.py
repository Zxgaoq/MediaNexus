"""
拉取 Windows 版 FFmpeg（完整版静态构建）到 resources/ffmpeg/
================================================================
用途：在打包（PyInstaller）之前运行一次，把 ffmpeg.exe / ffprobe.exe / ffplay.exe
放入 resources/ffmpeg/，使最终产物「内置 FFmpeg」，用户无需下载或配置。

为何选完整版静态构建：
  - 静态链接：每个 .exe 自包含，无 DLL 依赖地狱；
  - 完整版：含全部编解码器/滤镜，覆盖现有质检及后续扩展的全部需求；
  - 安装包随附后用户开箱即用、完全离线。

用法：
    python scripts/fetch_ffmpeg.py
默认下载 .7z（约 159 MB，需 py7zr）；若环境无 py7zr 则自动改用
同名 .zip（约 254 MB，仅用标准库）。可通过环境变量 FFMPEG_USE_ZIP=1
强制使用 zip。
"""
from __future__ import annotations

import os
import sys
import ssl
import shutil
import tempfile
import urllib.request
import zipfile

# gyan.dev 的 GitHub 镜像（CDN 稳定）。release 8.1.2 完整版静态构建。
# 包含 ffmpeg.exe + ffprobe.exe + ffplay.exe 及全部编解码器/滤镜。
FFMPEG_7Z_URL = "https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-full_build.7z"
FFMPEG_ZIP_URL = "https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-full_build.zip"

# 脚本位于 <repo>/scripts/fetch_ffmpeg.py，资源目录为 <repo>/resources/ffmpeg
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIR = os.path.join(REPO_ROOT, "resources", "ffmpeg")


def _stream_download(url: str, dest: str):
    """流式下载（带进度），支持标准库与 GitHub CDN 重定向。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "MediaNexus-Build/1.0"})
    last_err = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                chunk = 1 << 20
                with open(dest, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if total:
                            pct = min(100, int(downloaded / total * 100))
                            sys.stdout.write(f"\r  下载进度: {pct}%")
                            sys.stdout.flush()
            if total and os.path.getsize(dest) != total:
                raise IOError("文件大小校验失败，可能下载不完整")
            print(f"\n      已下载: {os.path.getsize(dest) / 1e6:.1f} MB")
            return
        except Exception as e:  # 重试
            last_err = e
            print(f"\n      [重试 {attempt}/3] 失败: {e}")
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except Exception:
                    pass
    raise RuntimeError(f"下载失败（已重试 3 次）: {last_err}")


def _extract(archive_path: str):
    """从压缩包中提取 ffmpeg.exe / ffprobe.exe / ffplay.exe 到 TARGET_DIR。"""
    needed = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe"}
    found = {}

    # 优先尝试 .7z（需 py7zr）
    if archive_path.endswith(".7z"):
        try:
            import py7zr  # type: ignore
        except Exception:
            raise RuntimeError(
                "提取 .7z 需要 py7zr，请先 `pip install py7zr`，"
                "或设置环境变量 FFMPEG_USE_ZIP=1 改用 .zip（仅标准库）。"
            )
        with py7zr.SevenZipFile(archive_path, "r") as zf:
            for name in zf.getnames():
                base = os.path.basename(name)
                if base in needed and base not in found:
                    zf.extract(path=TARGET_DIR, targets=[name])
                    found[base] = os.path.getsize(
                        os.path.join(TARGET_DIR, *name.split("/"))
                    )
    else:
        with zipfile.ZipFile(archive_path, "r") as zf:
            for name in zf.namelist():
                base = os.path.basename(name)
                if base in needed and base not in found:
                    dst = os.path.join(TARGET_DIR, base)
                    with zf.open(name) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
                    found[base] = os.path.getsize(dst)

    missing = needed - set(found)
    if missing:
        raise RuntimeError(f"压缩包内缺失: {missing}（请确认下载的是完整版构建）")
    return found


def main():
    os.makedirs(TARGET_DIR, exist_ok=True)
    use_zip = os.environ.get("FFMPEG_USE_ZIP") == "1"
    url = FFMPEG_ZIP_URL if use_zip else FFMPEG_7Z_URL
    ext = ".zip" if use_zip else ".7z"
    label = "zip(标准库)" if use_zip else "7z(py7zr)"

    print(f"[1/3] 下载完整版构建（{label}）：\n      {url}")
    tmp = tempfile.mkdtemp(prefix="medianexus_fffetch_")
    try:
        archive = os.path.join(tmp, "ffmpeg-full" + ext)
        _stream_download(url, archive)
        print("[2/3] 解压 ffmpeg.exe / ffprobe.exe ...")
        found = _extract(archive)
        print("[3/3] 完成。已写入 resources/ffmpeg/:")
        for name, size in sorted(found.items()):
            print(f"      {name:12s} {size / 1e6:7.1f} MB")
        total = sum(found.values())
        print(f"      合计: {total / 1e6:.1f} MB（已内置，用户无需下载）")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        print(f"\n[错误] 获取 FFmpeg 失败: {e}", file=sys.stderr)
        sys.exit(1)
