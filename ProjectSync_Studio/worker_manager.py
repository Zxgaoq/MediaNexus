# -*- coding: utf-8 -*-
"""
ProjectSync Studio - Worker 统一管理器
解决：
  1. closeEvent 中逐个等待 Worker 的脆弱性（统一注册 + 批量停止）
  2. 旧 Worker 结果回流覆盖新内容（generation 计数器）

用法：
    self._wm = WorkerManager()

    # 注册
    self._wm.register("index", index_worker)
    self._wm.register("list_right", list_worker)

    # 检查陈旧
    gen = self._wm.generation_for("list_right")
    # ... 在 slot 中:
    if self._wm.is_stale("list_right", gen):
        return  # 丢弃旧结果

    # 统一停止（closeEvent 中调用）
    self._wm.stop_all()
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QThread

logger = logging.getLogger("ProjectSync.WorkerManager")


class WorkerManager:
    """Worker 生命周期统一管理器。"""

    def __init__(self):
        self._workers: dict[str, QThread] = {}
        self._generations: dict[str, int] = {}

    # ── 注册 / 注销 ──

    def register(self, name: str, worker: QThread) -> None:
        """注册一个 Worker。同名重复注册会覆盖旧引用（旧的不会被自动停止）。"""
        self._workers[name] = worker
        logger.debug(f"Worker 已注册: {name}")

    def unregister(self, name: str) -> QThread | None:
        """注销并返回 Worker 引用（不停止）。"""
        return self._workers.pop(name, None)

    def get(self, name: str) -> QThread | None:
        """获取已注册的 Worker。"""
        return self._workers.get(name)

    # ── 陈旧结果防护 ──

    def generation_for(self, tag: str) -> int:
        """获取指定 tag 的当前代数并自增。

        用法：在启动新 Worker 前调用，保存返回的 gen 值。
        在 slot 回调中用 is_stale(tag, gen) 判断结果是否已过时。
        """
        gen = self._generations.get(tag, 0)
        self._generations[tag] = gen + 1
        return gen

    def is_stale(self, tag: str, gen: int) -> bool:
        """判断给定代数是否已过时（有更新的 Worker 已启动）。"""
        return self._generations.get(tag, 0) > gen + 1

    # ── 统一停止 ──

    def stop_all(self, timeout_per_worker: int = 1500) -> int:
        """停止所有已注册的运行中 Worker，返回实际等待的 Worker 数量。

        策略：
          1. 先并行发出所有停止信号（requestInterruption / quit）
          2. 再逐个 wait
        """
        running: list[tuple[str, QThread]] = []

        # 阶段 1：并行发信号
        for name, worker in self._workers.items():
            try:
                alive = worker and worker.isRunning()
            except RuntimeError:
                alive = False  # C++ 对象已销毁
            if alive:
                running.append((name, worker))
                try:
                    worker.requestInterruption()
                    if hasattr(worker, "quit"):
                        worker.quit()
                except Exception:
                    pass

        if not running:
            return 0

        # 阶段 2：逐个等待
        stopped = 0
        for name, worker in running:
            try:
                worker.wait(timeout_per_worker)
                stopped += 1
            except Exception:
                logger.warning(f"Worker {name} 停止超时")

        logger.info(f"WorkerManager: 已停止 {stopped}/{len(running)} 个 Worker")
        return stopped

    # ── 诊断 ──

    def running_count(self) -> int:
        """当前运行中的 Worker 数量。"""
        count = 0
        for w in self._workers.values():
            try:
                if w and w.isRunning():
                    count += 1
            except RuntimeError:
                pass  # C++ 对象已销毁
        return count

    def names(self) -> list[str]:
        """所有已注册的 Worker 名称。"""
        return list(self._workers.keys())
