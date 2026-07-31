# -*- coding: utf-8 -*-
"""
MediaNexus - NAS 索引器（异步 + SQLite）

设计要点：
  1. 使用 asyncio + aiofiles 异步遍历 NAS / UNC 网络路径，目录枚举的
     网络等待不阻塞事件循环，整体跑在 QThread 中 => UI 永远不卡顿。
  2. 索引写入本地 SQLite（WAL 模式），首扫后持久化，后续启动秒开。
  3. 支持进度回调、暂停/继续（pause_event）、中止（stop_event）。
  4. 单目录异常（权限不足/断连）被隔离，不影响整体索引。
  5. 表结构：
       entries(path PK, name, parent, is_dir, size, mtime)
       meta(key PK, value)
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import aiofiles.os as aios

from .constants import INDEX_DB_PATH, MAX_CONCURRENCY
import logging

logger = logging.getLogger("MediaNexus.Indexer")

ProgressCb = Callable[[int, int, str], None]  # (dirs, files, current_path)

# LIKE 转义字符。用普通可打印字符 `!` 而非反斜杠——若用 `ESCAPE '\'`，
# SQLite 会把 SQL 字符串字面量里的 `\'` 误解析为转义引号，报
# "ESCAPE expression must be a single character"。以参数绑定 `ESCAPE ?` 传入。
_LIKE_ESC = "!"


class NASIndexer:
    def __init__(self, db_path: Path = INDEX_DB_PATH):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._write_lock = None  # asyncio.Lock，在事件循环内创建
        # 写操作串行锁：rebuild / reindex_subtree 都会动 self._conn。
        # 全局单例被多个后台线程（IndexWorker / DeepScanWorker / 心跳 RefreshIndexWorker）
        # 共用，必须串行，否则会出现「同一连接跨线程使用」的原生崩溃。
        self._write_serial = threading.Lock()

    # --------------------------- 连接 / 建表 ---------------------------
    def _connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA cache_size=-65536")
        self._conn.execute("PRAGMA mmap_size=1073741824")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_size_limit=134217728")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                path    TEXT PRIMARY KEY,
                name    TEXT NOT NULL,
                parent  TEXT NOT NULL,
                is_dir  INTEGER NOT NULL,
                size    INTEGER NOT NULL DEFAULT 0,
                mtime   REAL NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entries_parent ON entries(parent)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entries_isdir ON entries(is_dir)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entries_name ON entries(name)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entries_parent_name ON entries(parent, name)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entries_mtime ON entries(mtime)"
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.commit()
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None

    # --------------------------- 对外入口：重建索引 ---------------------------
    def rebuild(
        self,
        roots: list[str],
        progress_cb: ProgressCb | None = None,
        pause_event=None,
        stop_event=None,
        fast: bool = False,
    ) -> dict:
        """全量重建索引。

        fast=True：仅扫描项目级目录（NAS 根的直接子级），速度快数十倍，
        用于快速发现可添加的项目；后续对已添加项目单独调用 deep_scan_projects。
        """
        start = datetime.now()
        logger.info(f"[rebuild] 开始: roots={roots}, fast={fast}")
        stats = {"dirs": 0, "files": 0, "errors": 0}
        max_depth = 1 if fast else -1
        with self._write_serial:
            try:
                asyncio.run(
                    self._walk(roots, stats, progress_cb, pause_event, stop_event,
                               clear=True, max_depth=max_depth)
                )
            except asyncio.CancelledError:
                logger.info("[rebuild] 已取消")
                pass
            finally:
                self.close()
        elapsed = (datetime.now() - start).total_seconds()
        result = {
            "dirs": stats["dirs"],
            "files": stats["files"],
            "errors": stats["errors"],
            "elapsed": round(elapsed, 1),
            "ok": stats["errors"] < 9999,
        }
        logger.info(
            f"[rebuild] 完成: dirs={result['dirs']}, files={result['files']}, "
            f"errors={result['errors']}, elapsed={result['elapsed']}s"
        )
        return result

    # --------------------------- 异步遍历核心（安全生产者-消费者） ---------------------------
    async def _walk(
        self,
        roots: list[str],
        stats: dict,
        progress_cb: ProgressCb | None,
        pause_event,
        stop_event,
        clear: bool = True,
        max_depth: int = -1,
    ) -> None:
        self._connect()
        self._write_lock = asyncio.Lock()
        if clear:
            self._conn.execute("DELETE FROM entries")
            self._conn.commit()

        queue: asyncio.Queue = asyncio.Queue()
        for r in roots:
            r = r.rstrip("/\\")
            if r:
                await queue.put((r, r, 0))  # (当前目录, 父目录, 深度)

        last_report = {"dirs": 0}

        async def worker() -> None:
            while True:
                # 暂停等待
                if pause_event and pause_event.is_set():
                    while pause_event.is_set():
                        if stop_event and stop_event.is_set():
                            return
                        await asyncio.sleep(0.1)

                if stop_event and stop_event.is_set():
                    return

                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                if item is None:
                    queue.task_done()
                    return

                try:
                    subdirs = await self._scan_dir(item, stats)
                    depth = item[2]
                    if max_depth < 0 or depth < max_depth:
                        for sd in subdirs:
                            await queue.put((sd, item[0], depth + 1))
                except Exception:  # noqa: BLE001 单目录失败隔离
                    stats["errors"] += 1
                finally:
                    queue.task_done()
                    if progress_cb and (stats["dirs"] - last_report["dirs"]) >= 50:
                        last_report["dirs"] = stats["dirs"]
                        progress_cb(stats["dirs"], stats["files"], "")

        workers = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENCY)]
        try:
            while True:
                if stop_event and stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(queue.join(), timeout=0.1)
                    break
                except asyncio.TimeoutError:
                    continue
        finally:
            for _ in workers:
                await queue.put(None)
            await asyncio.gather(*workers, return_exceptions=True)

        if progress_cb:
            progress_cb(stats["dirs"], stats["files"], "索引完成")
        self._set_meta("indexed_at", datetime.now().isoformat(timespec="seconds"))

    # --------------------------- 增量子树重建（供「刷新」/心跳） ---------------------------
    @staticmethod
    def _like_escape(prefix: str) -> str:
        """转义 LIKE 特殊字符（! % _ \），使前缀精确匹配，避免含下划线/反斜杠的路径误匹配。"""
        return prefix.replace("!", "!!").replace("\\", "!\\").replace("%", "!%").replace("_", "!_")

    def reindex_subtree(self, root: str) -> dict:
        """增量重建单个子树（root 及其所有后代）的索引。

        先删除该子树下的旧条目（含 root 自身），再重新走查并 INSERT OR REPLACE，
        因此被删除的文件会自然消失、新增/修改的会更新。返回统计 dict。
        较「全量 rebuild」只动一个项目子树，对 NAS 压力小得多。
        """
        root = root.rstrip("/\\")
        if not root:
            return {"dirs": 0, "files": 0, "errors": 0}
        logger.info(f"[reindex_subtree] 开始: root={root!r}")
        with self._write_serial:
            self._connect()
            # 删除旧子树条目（含 root 自身），兼容 / 与 \\ 两种分隔符
            esc = self._like_escape(root)
            pat_fwd = esc + "/%"
            pat_bwd = esc + "\\%"
            self._conn.execute(
                "DELETE FROM entries WHERE path=? OR parent=? "
                "OR path LIKE ? ESCAPE ? OR path LIKE ? ESCAPE ?",
                (root, root, pat_fwd, _LIKE_ESC, pat_bwd, _LIKE_ESC),
            )
            self._conn.commit()
            stats = {"dirs": 0, "files": 0, "errors": 0}
            try:
                asyncio.run(self._walk_subtree(root, stats))
            except asyncio.CancelledError:
                logger.info(f"[reindex_subtree] 已取消: root={root!r}")
                pass
            finally:
                self.close()
        logger.info(
            f"[reindex_subtree] 完成: root={root!r}, "
            f"dirs={stats['dirs']}, files={stats['files']}, errors={stats['errors']}"
        )
        return stats

    # --------------------------- 增量单级刷新（watcher 事件驱动） ---------------------------
    def refresh_dir(self, dir_path: str) -> dict:
        """单级增量刷新：scandir 一次 → diff → 增删改。

        由 watcher changed 信号驱动。只处理 dir_path 的直接子项，不递归。
        若当前有全量扫描在跑（_write_serial 被占），则跳过（全量扫描已覆盖）。
        返回 {"added": n, "updated": n, "removed": n}。
        """
        dir_path = dir_path.rstrip("/\\")
        result = {"added": 0, "updated": 0, "removed": 0}

        # 尝试获取写锁（短超时）——全量扫描在跑时跳过
        if not self._write_serial.acquire(timeout=2.0):
            logger.debug(f"[refresh_dir] 写锁忙，跳过: {dir_path!r}")
            return result

        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")

            # 1. scandir 获取当前实际内容
            current: dict[str, tuple] = {}  # path -> (name, is_dir, size, mtime)
            try:
                with os.scandir(dir_path) as it:
                    for entry in it:
                        try:
                            is_dir = entry.is_dir()
                            try:
                                st = entry.stat()
                                size = 0 if is_dir else st.st_size
                                mtime = st.st_mtime
                            except OSError:
                                size, mtime = 0, 0
                            current[entry.path] = (entry.name, is_dir, size, mtime)
                        except OSError:
                            continue
            except (OSError, PermissionError):
                # 目录不可访问（可能已被删除）——跳过
                conn.close()
                return result

            # 2. 查询索引中该目录下的现有条目
            cur = conn.execute(
                "SELECT path, name, is_dir, size, mtime FROM entries WHERE parent=?",
                (dir_path,),
            )
            indexed: dict[str, tuple] = {}
            for row in cur.fetchall():
                indexed[row[0]] = (row[1], bool(row[2]), row[3], row[4])

            # 3. Diff：新增 / 修改 / 删除
            to_insert = []
            to_update = []
            to_delete = []

            for path, (name, is_dir, size, mtime) in current.items():
                if path not in indexed:
                    to_insert.append(
                        (path, name, dir_path, 1 if is_dir else 0, size, mtime)
                    )
                    result["added"] += 1
                else:
                    _, _, old_size, old_mtime = indexed[path]
                    if size != old_size or abs(mtime - old_mtime) > 0.01:
                        to_update.append((size, mtime, path))
                        result["updated"] += 1

            for path in indexed:
                if path not in current:
                    to_delete.append(path)
                    result["removed"] += 1

            # 4. 单事务应用变更
            if to_insert or to_update or to_delete:
                if to_insert:
                    conn.executemany(
                        "INSERT OR REPLACE INTO entries(path,name,parent,is_dir,size,mtime) "
                        "VALUES(?,?,?,?,?,?)",
                        to_insert,
                    )
                if to_update:
                    conn.executemany(
                        "UPDATE entries SET size=?, mtime=? WHERE path=?",
                        to_update,
                    )
                if to_delete:
                    for path in to_delete:
                        # 若删除的是目录，连带清除其整个子树
                        row = conn.execute(
                            "SELECT is_dir FROM entries WHERE path=?", (path,)
                        ).fetchone()
                        if row and row[0]:
                            esc = self._like_escape(path)
                            conn.execute(
                                "DELETE FROM entries WHERE path=? "
                                "OR path LIKE ? ESCAPE ? OR path LIKE ? ESCAPE ?",
                                (path, esc + "/%", _LIKE_ESC, esc + "\\%", _LIKE_ESC),
                            )
                        else:
                            conn.execute("DELETE FROM entries WHERE path=?", (path,))
                conn.commit()

            conn.close()
        except sqlite3.Error as e:
            logger.warning(f"[refresh_dir] SQLite 错误: {dir_path!r}: {e}")
        finally:
            self._write_serial.release()

        if any(result.values()):
            logger.debug(
                f"[refresh_dir] {dir_path!r}: "
                f"+{result['added']} ~{result['updated']} -{result['removed']}"
            )
        return result

    def refresh_dirs(self, dir_paths: list[str]) -> dict:
        """批量增量刷新多个目录（watcher 防抖后一次传入多个受影响目录）。

        逐目录调用 refresh_dir，汇总统计。每个目录独立事务，
        单个目录失败不影响其余。
        """
        total = {"added": 0, "updated": 0, "removed": 0}
        for d in dir_paths:
            try:
                r = self.refresh_dir(d)
                for k in total:
                    total[k] += r[k]
            except Exception as e:  # noqa: BLE001 单目录失败隔离
                logger.warning(f"[refresh_dirs] 刷新失败 {d!r}: {e}")
        return total

    async def _walk_subtree(self, root: str, stats: dict) -> None:
        """只遍历 root 子树，INSERT OR REPLACE 写入索引（不清空其他条目）。"""
        self._write_lock = asyncio.Lock()
        # 先写入 root 目录自身（带 mtime）
        try:
            st = os.stat(root)
            size, mtime = 0, st.st_mtime
        except OSError:
            size, mtime = 0, 0
        parent = os.path.dirname(root.rstrip("/\\")) or root
        name = os.path.basename(root.rstrip("/\\")) or root
        async with self._write_lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO entries(path,name,parent,is_dir,size,mtime) "
                "VALUES(?,?,?,?,?,?)",
                (root, name, parent, 1, size, mtime),
            )
            self._conn.commit()
        # BFS 遍历子树
        queue: asyncio.Queue = asyncio.Queue()
        await queue.put((root, root))

        async def worker() -> None:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if item is None:
                    queue.task_done()
                    return
                try:
                    subdirs = await self._scan_dir(item, stats)
                    for sd in subdirs:
                        await queue.put((sd, item[0]))
                except Exception:  # noqa: BLE001 单目录失败隔离
                    stats["errors"] += 1
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENCY)]
        try:
            while True:
                try:
                    await asyncio.wait_for(queue.join(), timeout=0.1)
                    break
                except asyncio.TimeoutError:
                    continue
        finally:
            for _ in workers:
                await queue.put(None)
            await asyncio.gather(*workers, return_exceptions=True)

    async def _scan_dir(self, item, stats) -> list[str]:
        """
        扫描单个目录，返回其子目录路径列表。
        目录/文件元信息批量写入 SQLite（加锁保证单连接安全）。
        """
        dir_path = item[0]
        rows = []
        subdirs = []
        try:
            # aiofiles 25.x：scandir 是协程（把「打开目录」这一步 offload 到线程池，
            # 返回的是原生同步迭代器 nt.ScandirIterator；逐条 entry 的 is_dir()/stat()
            # 在 Windows 上直接复用 FindFirstFile 已缓存的元数据，几乎零额外网络开销。
            it = await aios.scandir(dir_path)
        except (OSError, PermissionError) as e:  # noqa: BLE001
            stats["errors"] += 1
            logger.debug(f"[_scan_dir] 无法访问: {dir_path!r} ({e})")
            return subdirs
        try:
            for entry in it:
                try:
                    name = entry.name
                    is_dir = entry.is_dir()
                    try:
                        st = entry.stat()
                        size = 0 if is_dir else st.st_size
                        mtime = st.st_mtime
                    except OSError:
                        size, mtime = 0, 0
                    rows.append((entry.path, name, dir_path, 1 if is_dir else 0, size, mtime))
                    if is_dir:
                        subdirs.append(entry.path)
                        stats["dirs"] += 1
                    else:
                        stats["files"] += 1
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError) as e:  # noqa: BLE001 scandir 迭代中途失败
            stats["errors"] += 1
            logger.debug(f"[_scan_dir] 迭代中断: {dir_path!r} ({e})")
        # 批量写入
        async with self._write_lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO entries(path,name,parent,is_dir,size,mtime) "
                "VALUES(?,?,?,?,?,?)",
                rows,
            )
            self._conn.commit()
        return subdirs

    # --------------------------- 查询接口（供匹配 / UI 使用） ---------------------------
    def _open_ro(self):
        """打开一个独立的只读连接（由当前调用线程拥有），用于查询。

        关键修复：不再复用 self._conn——后台扫描/心跳刷新线程可能正持有它的
        读写连接，GUI 线程若复用跨线程连接会触发 SQLite 异常，使调用方静默退化
        (如添加项目窗口只显示本地)。每次调用都新建/关闭独立连接，配合 WAL 模式
        天然支持一写多读。
        """
        if not Path(self.db_path).exists():
            return None
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only=on")
            conn.execute("PRAGMA cache_size=-65536")
            conn.execute("PRAGMA mmap_size=1073741824")
            conn.execute("PRAGMA temp_store=MEMORY")
        except sqlite3.Error:
            pass
        return conn

    def query_all_folders(self) -> list[str]:
        """返回所有已索引文件夹的完整路径（作为匹配候选）。"""
        conn = self._open_ro()
        if not conn:
            return []
        try:
            cur = conn.execute("SELECT path FROM entries WHERE is_dir=1")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def get_folder_mtime(self, path: str, default: float = 0.0) -> float:
        """返回某文件夹自身的 mtime（用于项目按服务器时间排序）。未索引返回 default。"""
        conn = self._open_ro()
        if not conn:
            return default
        try:
            cur = conn.execute("SELECT mtime FROM entries WHERE path=?", (path,))
            row = cur.fetchone()
            return float(row[0]) if row else default
        finally:
            conn.close()

    def list_children(self, parent_path: str) -> list[dict]:
        """返回某目录下的直接子项，文件夹在前、按名称排序。供右栏虚拟列表懒加载。"""
        conn = self._open_ro()
        if not conn:
            return []
        try:
            cur = conn.execute(
                "SELECT path,name,is_dir,size,mtime FROM entries WHERE parent=? "
                "ORDER BY is_dir DESC, name COLLATE NOCASE ASC",
                (parent_path,),
            )
            return [
                {"path": r[0], "name": r[1], "is_dir": bool(r[2]), "size": r[3], "mtime": r[4]}
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value)
        )
        self._conn.commit()



# 全局索引器单例
indexer = NASIndexer()
