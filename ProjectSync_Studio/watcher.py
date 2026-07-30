# -*- coding: utf-8 -*-
"""
ProjectSync Studio - NAS 实时文件监控

使用 Windows ReadDirectoryChangesW API（与资源管理器相同机制）递归监控
NAS/UNC 目录，实时捕获文件与文件夹的创建、删除、重命名、内容修改。

设计：
  - 每个被监控的项目根目录对应一个 NASWatchThread（QThread）
  - 阻塞的 ReadDirectoryChangesW 跑在 daemon 子线程中，通过 queue 回传事件
  - QThread 以 300ms 超时轮询 queue，收到事件后做防抖合并并发出 changed 信号
  - stop() 只需设 _stop_event，QThread 在 300ms 内退出，daemon 线程随进程消亡
  - 连接断开时自动检测并尝试重连

依赖：pywin32（已在 requirements.txt 中）
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("ProjectSync.Watcher")

# Windows API 常量
FILE_LIST_DIRECTORY = 0x0001
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

# 监控的变更类型（与资源管理器一致）
FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001   # 文件创建/删除/重命名
FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002    # 目录创建/删除/重命名
FILE_NOTIFY_CHANGE_SIZE = 0x00000008        # 文件大小变化
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010  # 文件内容修改（保存）
FILE_NOTIFY_CHANGE_CREATION = 0x00000040    # 创建时间变化

WATCH_FLAGS = (
    FILE_NOTIFY_CHANGE_FILE_NAME
    | FILE_NOTIFY_CHANGE_DIR_NAME
    | FILE_NOTIFY_CHANGE_SIZE
    | FILE_NOTIFY_CHANGE_LAST_WRITE
    | FILE_NOTIFY_CHANGE_CREATION
)

# 事件动作类型
FILE_ACTION_ADDED = 0x00000001
FILE_ACTION_REMOVED = 0x00000002
FILE_ACTION_MODIFIED = 0x00000003
FILE_ACTION_RENAMED_OLD_NAME = 0x00000004
FILE_ACTION_RENAMED_NEW_NAME = 0x00000005

# 防抖窗口（秒）：合并短时间内的批量事件
DEBOUNCE_INTERVAL = 0.5
# 重连间隔（秒）
RECONNECT_INTERVAL = 5.0
# 读取缓冲区大小（64KB，足够容纳数百个事件）
BUFFER_SIZE = 65536
# QThread 轮询 queue 的超时（秒）——决定 stop() 后的最大退出延迟
POLL_TIMEOUT = 0.3


class NASWatchThread(QThread):
    """单个目录的实时监控线程。

    架构：阻塞的 ReadDirectoryChangesW 跑在 daemon 子线程中，
    通过 queue 回传事件。QThread 以短超时轮询 queue，
    stop() 后 QThread 在 POLL_TIMEOUT 内退出，不依赖中断阻塞调用。

    Signals:
        changed(str, list): (root_path, [affected_dir_paths]) — 防抖后批量发出
        error(str, str): (root_path, error_message) — 监控出错
        connected(str): (root_path) — 成功建立监控
        disconnected(str): (root_path) — 连接丢失
        overflow(str): (root_path) — 事件缓冲区溢出，需要全量刷新
    """

    changed = Signal(str, list)
    error = Signal(str, str)
    connected = Signal(str)
    disconnected = Signal(str)
    overflow = Signal(str)

    def __init__(self, root_path: str, parent=None):
        super().__init__(parent)
        self._root = root_path.rstrip("/\\")
        self._stop_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()

    @property
    def root(self) -> str:
        return self._root

    def stop(self):
        """请求停止监控。QThread 将在 POLL_TIMEOUT 内退出。"""
        self._stop_event.set()

    def run(self):
        """QThread 主体：启动 daemon 读取线程 → 轮询 queue → 防抖 → 发信号。"""
        # 启动 daemon 子线程做阻塞的 ReadDirectoryChangesW
        reader = threading.Thread(
            target=self._blocking_reader, daemon=True, name=f"watcher-io-{self._root}"
        )
        reader.start()

        # 事件收集 + 防抖
        pending_dirs: set[str] = set()
        last_flush = time.monotonic()

        while not self._stop_event.is_set():
            # 从 queue 取事件（短超时，确保 stop 信号快速响应）
            try:
                msg = self._queue.get(timeout=POLL_TIMEOUT)
            except queue.Empty:
                # 超时：检查是否有待发送的事件
                if pending_dirs:
                    now = time.monotonic()
                    if (now - last_flush) >= DEBOUNCE_INTERVAL:
                        self.changed.emit(self._root, list(pending_dirs))
                        pending_dirs.clear()
                        last_flush = now
                continue

            # 处理 daemon 线程发来的消息
            kind = msg[0]
            if kind == "results":
                # msg = ("results", [(action, filename), ...])
                for action, filename in msg[1]:
                    if not filename:
                        continue
                    full_path = os.path.join(self._root, filename)
                    parent = os.path.dirname(full_path)
                    pending_dirs.add(parent)
            elif kind == "connected":
                self.connected.emit(self._root)
            elif kind == "disconnected":
                self.disconnected.emit(self._root)
            elif kind == "error":
                self.error.emit(self._root, msg[1])
            elif kind == "overflow":
                self.overflow.emit(self._root)

            # 防抖：累积事件，超过间隔后批量发出
            if pending_dirs:
                now = time.monotonic()
                if (now - last_flush) >= DEBOUNCE_INTERVAL:
                    self.changed.emit(self._root, list(pending_dirs))
                    pending_dirs.clear()
                    last_flush = now

        # 退出前发送剩余事件
        if pending_dirs:
            self.changed.emit(self._root, list(pending_dirs))

        logger.info(f"[watcher] 已停止: {self._root!r}")

    def _blocking_reader(self):
        """Daemon 线程：执行阻塞的 ReadDirectoryChangesW，通过 queue 回传事件。

        此线程在 stop() 后可能仍阻塞在 ReadDirectoryChangesW 中（NAS 路径下
        CloseHandle 不能可靠中断），但因为是 daemon 线程，进程退出时自动消亡。
        """
        import win32file
        import pywintypes

        while not self._stop_event.is_set():
            # 打开目录句柄
            try:
                handle = win32file.CreateFile(
                    self._root,
                    FILE_LIST_DIRECTORY,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                    None,
                    OPEN_EXISTING,
                    FILE_FLAG_BACKUP_SEMANTICS,
                    None,
                )
            except pywintypes.error as e:
                if self._stop_event.is_set():
                    return
                logger.warning(f"[watcher] 无法打开目录 {self._root!r}: {e}")
                self._queue.put(("error", str(e)))
                # 短间隔等待重连
                for _ in range(int(RECONNECT_INTERVAL / POLL_TIMEOUT)):
                    if self._stop_event.wait(POLL_TIMEOUT):
                        return
                continue

            self._queue.put(("connected",))
            logger.info(f"[watcher] 开始监控: {self._root!r}")

            try:
                while not self._stop_event.is_set():
                    # 阻塞等待变更通知（可能无限期阻塞，由 daemon 属性保证进程退出时清理）
                    try:
                        results = win32file.ReadDirectoryChangesW(
                            handle,
                            BUFFER_SIZE,
                            True,  # bWatchSubtree = 递归监控子目录
                            WATCH_FLAGS,
                        )
                    except pywintypes.error as e:
                        if self._stop_event.is_set():
                            return
                        # 连接丢失
                        logger.info(f"[watcher] 连接丢失: {self._root!r} ({e})")
                        self._queue.put(("disconnected",))
                        break

                    # 缓冲区溢出检测
                    if not results:
                        logger.warning(f"[watcher] 缓冲区溢出: {self._root!r}")
                        self._queue.put(("overflow",))
                        continue

                    self._queue.put(("results", results))

            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"[watcher] 监控异常: {self._root!r}: {e}")
                    self._queue.put(("error", str(e)))
            finally:
                try:
                    win32file.CloseHandle(handle)
                except Exception:
                    pass

            # 非主动停止 → 短间隔等待后重连
            if not self._stop_event.is_set():
                for _ in range(int(RECONNECT_INTERVAL / POLL_TIMEOUT)):
                    if self._stop_event.wait(POLL_TIMEOUT):
                        return


class NASWatcherManager:
    """管理多个 NASWatchThread 的生命周期。

    用法：
        mgr = NASWatcherManager()
        mgr.on_changed = lambda root, dirs: ...  # 设置回调
        mgr.watch("\\\\NAS\\Projects\\ShowA")
        mgr.unwatch("\\\\NAS\\Projects\\ShowA")
        mgr.stop_all()
    """

    def __init__(self):
        self._threads: dict[str, NASWatchThread] = {}
        self.on_changed: callable | None = None  # (root, affected_dirs) -> None
        self.on_connected: callable | None = None
        self.on_disconnected: callable | None = None
        self.on_error: callable | None = None
        self.on_overflow: callable | None = None  # (root) -> None  缓冲区溢出

    def watch(self, root_path: str) -> None:
        """开始监控一个目录（已监控则跳过）。"""
        root = root_path.rstrip("/\\")
        if root in self._threads:
            t = self._threads[root]
            if t.isRunning():
                return
        thread = NASWatchThread(root)
        thread.changed.connect(self._handle_changed)
        thread.connected.connect(self._handle_connected)
        thread.disconnected.connect(self._handle_disconnected)
        thread.error.connect(self._handle_error)
        thread.overflow.connect(self._handle_overflow)
        self._threads[root] = thread
        thread.start()
        logger.info(f"[watcher_mgr] 已启动监控: {root!r}")

    def unwatch(self, root_path: str) -> None:
        """停止监控一个目录。"""
        root = root_path.rstrip("/\\")
        thread = self._threads.pop(root, None)
        if thread:
            thread.stop()
            thread.wait(1000)
            logger.info(f"[watcher_mgr] 已停止监控: {root!r}")

    def stop_all(self) -> None:
        """停止所有监控线程。

        并行发 stop 信号 → 统一等待。QThread 在 POLL_TIMEOUT（300ms）内退出，
        daemon 读取线程随进程消亡，不阻塞关闭。
        """
        threads = list(self._threads.values())
        # 第一步：并行发送停止信号
        for thread in threads:
            thread.stop()
        # 第二步：统一等待（每个最多 1s，实际 ~300ms 即退出）
        for thread in threads:
            thread.wait(1000)
        self._threads.clear()
        if threads:
            logger.info(f"[watcher_mgr] 已停止所有监控（{len(threads)} 个）")

    def watching_roots(self) -> list[str]:
        """当前正在监控的目录列表。"""
        return [r for r, t in self._threads.items() if t.isRunning()]

    def _handle_changed(self, root: str, dirs: list):
        if self.on_changed:
            self.on_changed(root, dirs)

    def _handle_connected(self, root: str):
        if self.on_connected:
            self.on_connected(root)

    def _handle_disconnected(self, root: str):
        if self.on_disconnected:
            self.on_disconnected(root)

    def _handle_error(self, root: str, msg: str):
        if self.on_error:
            self.on_error(root, msg)

    def _handle_overflow(self, root: str):
        if self.on_overflow:
            self.on_overflow(root)
