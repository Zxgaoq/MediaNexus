"""
MediaNexus 防回归冒烟测试
================================================================
覆盖核心引擎模块（不依赖 GUI，可CI/本地快速运行）：
  - 版本与默认配置契约
  - 索引器：重建 / 列出子项 / 长时间并发写不跨线程崩溃
  - 匹配器：归一化不抛异常
  - FFmpeg 内置管理：解析接口与手动指定可用

运行：python -m pytest tests/ -q
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from MediaNexus import constants
from MediaNexus import config_manager
from MediaNexus import indexer
from MediaNexus import matcher
from utils.ffmpeg_manager import FFmpegManager
from utils.storage_manager import StorageManager


# --------------------------- 配置契约 ---------------------------
def test_version_is_1_1_0():
    assert constants.APP_VERSION == "1.1.0"


def test_default_ignore_patterns_empty():
    # 用户要求：忽略关键词默认空，避免误伤
    assert constants.DEFAULT_IGNORE_PATTERNS == []


# --------------------------- 索引器 ---------------------------
def _make_tree(root: str, sub: list[str]):
    os.makedirs(root)
    for s in sub:
        os.makedirs(os.path.join(root, s))


def test_indexer_rebuild_and_list_children():
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "NAS")
        _make_tree(root, ["ProjA", "ProjB"])
        db = os.path.join(tmp, "idx.db")
        idx = indexer.NASIndexer(db_path=db)
        stats = idx.rebuild([root], fast=True)
        idx.close()
        # fast 模式只索引根及其直接子目录；数量取决于实现，仅作健全性校验
        assert stats["dirs"] >= 2

        idx2 = indexer.NASIndexer(db_path=db)
        kids = idx2.list_children(root)
        names = sorted(k["name"] for k in kids)
        assert names == ["ProjA", "ProjB"]
        idx2.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_indexer_concurrent_writes_no_cross_thread_crash():
    """长时运行稳定性护栏：双线程并发写单例，验证 _write_serial 锁生效。"""
    tmp = tempfile.mkdtemp()
    try:
        r1 = os.path.join(tmp, "A")
        r2 = os.path.join(tmp, "B")
        _make_tree(r1, ["x"])
        _make_tree(r2, ["y"])
        db = os.path.join(tmp, "i.db")
        idx = indexer.NASIndexer(db_path=db)
        idx.rebuild([r1, r2], fast=True)
        idx.close()

        errors = []

        def worker(root):
            try:
                for _ in range(40):
                    idx.reindex_subtree(root)
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        t1 = threading.Thread(target=worker, args=(r1,))
        t2 = threading.Thread(target=worker, args=(r2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert not errors, f"并发写出现错误: {errors}"
        idx.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_indexer_read_isolated_from_write_connection():
    """读取必须走独立只读连接，不受后台写线程持有的 _conn 影响。"""
    tmp = tempfile.mkdtemp()
    try:
        import sqlite3
        root = os.path.join(tmp, "NAS")
        _make_tree(root, ["ProjA", "ProjB"])
        db = os.path.join(tmp, "idx.db")
        idx = indexer.NASIndexer(db_path=db)
        idx.rebuild([root], fast=True)
        idx.close()

        # 模拟后台写线程占用单例的 _conn
        idx._conn = sqlite3.connect(":memory:")
        kids = idx.list_children(root)
        names = sorted(k["name"] for k in kids)
        assert names == ["ProjA", "ProjB"]
        idx._conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------- 增量刷新（watcher 驱动） ---------------------------
def test_refresh_dir_detects_new_file():
    """新增文件后 refresh_dir 应在索引中体现。"""
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "NAS")
        os.makedirs(root)
        db = os.path.join(tmp, "idx.db")
        idx = indexer.NASIndexer(db_path=db)
        idx.rebuild([root], fast=True)
        idx.close()

        # 新增文件
        new_file = os.path.join(root, "new_file.txt")
        with open(new_file, "w") as f:
            f.write("hello")

        idx2 = indexer.NASIndexer(db_path=db)
        result = idx2.refresh_dir(root)
        idx2.close()
        assert result["added"] >= 1, f"应检测到新增文件，实际: {result}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refresh_dir_detects_removed_file():
    """删除文件后 refresh_dir 应在索引中移除。"""
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "NAS")
        os.makedirs(root)
        old_file = os.path.join(root, "old_file.txt")
        with open(old_file, "w") as f:
            f.write("data")
        db = os.path.join(tmp, "idx.db")
        idx = indexer.NASIndexer(db_path=db)
        idx.rebuild([root], fast=True)
        idx.close()

        # 删除文件
        os.remove(old_file)

        idx2 = indexer.NASIndexer(db_path=db)
        result = idx2.refresh_dir(root)
        idx2.close()
        assert result["removed"] >= 1, f"应检测到删除文件，实际: {result}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refresh_dir_detects_modified_file():
    """文件内容修改后 refresh_dir 应更新 size/mtime。"""
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "NAS")
        os.makedirs(root)
        mod_file = os.path.join(root, "mod.txt")
        with open(mod_file, "w") as f:
            f.write("short")
        db = os.path.join(tmp, "idx.db")
        idx = indexer.NASIndexer(db_path=db)
        idx.rebuild([root], fast=True)
        idx.close()

        # 修改文件内容（增加大小）
        import time
        time.sleep(0.1)  # 确保 mtime 变化
        with open(mod_file, "w") as f:
            f.write("much longer content here")

        idx2 = indexer.NASIndexer(db_path=db)
        result = idx2.refresh_dir(root)
        idx2.close()
        assert result["updated"] >= 1, f"应检测到修改文件，实际: {result}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refresh_dirs_batch():
    """批量 refresh_dirs 应汇总多个目录的变更。"""
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "NAS")
        sub_a = os.path.join(root, "A")
        sub_b = os.path.join(root, "B")
        os.makedirs(sub_a)
        os.makedirs(sub_b)
        db = os.path.join(tmp, "idx.db")
        idx = indexer.NASIndexer(db_path=db)
        idx.rebuild([root], fast=True)
        idx.close()

        # 两个子目录各新增一个文件
        with open(os.path.join(sub_a, "new_a.txt"), "w") as f:
            f.write("a")
        with open(os.path.join(sub_b, "new_b.txt"), "w") as f:
            f.write("b")

        idx2 = indexer.NASIndexer(db_path=db)
        result = idx2.refresh_dirs([sub_a, sub_b])
        idx2.close()
        assert result["added"] >= 2, f"应检测到两个新增文件，实际: {result}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refresh_dir_removes_directory_subtree():
    """删除目录后 refresh_dir 应连带清除其子树索引条目。"""
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "NAS")
        sub = os.path.join(root, "ToDelete")
        os.makedirs(os.path.join(sub, "inner"))
        with open(os.path.join(sub, "inner", "file.txt"), "w") as f:
            f.write("x")
        db = os.path.join(tmp, "idx.db")
        idx = indexer.NASIndexer(db_path=db)
        idx.rebuild([root], fast=False)  # 全量扫描以包含子目录
        idx.close()

        # 确认子目录已在索引中
        idx2 = indexer.NASIndexer(db_path=db)
        kids_before = idx2.list_children(root)
        names_before = [k["name"] for k in kids_before]
        assert "ToDelete" in names_before

        # 删除整个子目录
        shutil.rmtree(sub)

        idx2.refresh_dir(root)
        # 检查子树条目已被清除
        kids_after = idx2.list_children(root)
        names_after = [k["name"] for k in kids_after]
        assert "ToDelete" not in names_after, f"删除的目录不应出现在索引中: {names_after}"
        idx2.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------- Watcher 停止速度 ---------------------------
def test_watcher_stop_does_not_hang():
    """NASWatchThread.stop() 后线程应在 1 秒内退出（不阻塞关闭流程）。"""
    try:
        import win32file  # noqa: F401
    except ImportError:
        import pytest
        pytest.skip("pywin32 not available")

    from PySide6.QtWidgets import QApplication
    from MediaNexus.watcher import NASWatchThread
    import time

    # 确保 QApplication 存在（QThread 需要）
    QApplication.instance() or QApplication([])

    tmp = tempfile.mkdtemp()
    try:
        thread = NASWatchThread(tmp)
        thread.start()
        # 等待线程启动并进入监控
        time.sleep(0.5)
        assert thread.isRunning(), "线程应已启动"

        # 停止并计时
        t0 = time.monotonic()
        thread.stop()
        exited = thread.wait(2000)  # 最多等 2 秒
        elapsed = time.monotonic() - t0

        assert exited, f"线程应在 2s 内退出，实际耗时 {elapsed:.2f}s"
        assert elapsed < 1.5, f"线程退出太慢: {elapsed:.2f}s（应 < 1.5s）"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------- 匹配器 ---------------------------
def test_matcher_normalize_name():
    out = matcher.normalize_name("测试 项目 EP01 (1080p)")
    assert isinstance(out, str)

    out2 = matcher.normalize_name("My_Drama_S01E03_FINAL.mov")
    assert isinstance(out2, str)


def test_matcher_score_pair_monotonic():
    # 同名应得高分，差异大应得低分
    high = matcher.score_pair("测试项目", "测试项目")[0]
    low = matcher.score_pair("测试项目", "完全无关的素材名xyz")[0]
    assert high > low


# --------------------------- FFmpeg 管理器 ---------------------------
def test_ffmpeg_manager_interface():
    m = FFmpegManager()
    assert hasattr(m, "is_available")
    assert isinstance(m.is_available, bool)
    assert m.ffmpeg_path and m.ffprobe_path  # 至少有预期路径


def test_ffmpeg_manual_dir_resolves():
    tmp = tempfile.mkdtemp()
    try:
        f = os.path.join(tmp, "ffmpeg.exe")
        p = os.path.join(tmp, "ffprobe.exe")
        open(f, "w").close()
        open(p, "w").close()
        m = FFmpegManager()
        ok = m.set_manual_dir(tmp)
        assert ok is True
        assert m.is_available
    finally:
        # 清理对真实配置的单例写入，避免污染
        try:
            config_manager.ffmpeg_manual_dir = ""
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------- 存储管理 ---------------------------
def test_storage_audio_cache_is_listed_and_clearable():
    """音频提取缓存必须出现在缓存管理契约中，并可单独清理。"""
    tmp = tempfile.mkdtemp()
    try:
        storage = object.__new__(StorageManager)
        storage._initialized = True
        storage._base_dir = tmp
        storage._ensure_dirs()

        audio_dir = os.path.join(tmp, "data", "cache", "audio")
        os.makedirs(audio_dir)
        payload = os.path.join(audio_dir, "sample_extracted.wav")
        with open(payload, "wb") as f:
            f.write(b"audio-cache")

        info = storage.get_all_cache_info()
        audio_item = next(item for item in info["items"] if item["id"] == "audio_cache")
        assert audio_item["file_count"] == 1
        assert audio_item["size_mb"] >= 0

        result = storage.clear_all_caches({"audio_cache"})
        assert not os.path.exists(payload)
        assert result["errors"] == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
