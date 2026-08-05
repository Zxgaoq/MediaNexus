# -*- coding: utf-8 -*-
"""
QC 检测器统一接口与注册表

所有检测器继承 BaseDetector 并注册到 DetectorRegistry，
DetectionEngine 通过注册表遍历调用，新增检测项只需：
  1. 在 core/ 下新建文件实现 BaseDetector
  2. 在 registry.py 底部注册一行

这样 engine.py / qc_gui / exporter 都不需要为新检测器改动。
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("MediaNexus.QC.Detector")


@dataclass
class DetectionContext:
    """传递给每个检测器的上下文，包含所有可能需要的数据。

    各检测器按需使用其中的字段，不需要全部消费。
    """

    filepath: str                              # 视频文件路径（静音检测用）
    metadata: dict | None = None               # FFprobe 元数据
    fps: float = 25.0                          # 帧率
    thumbs: list = field(default_factory=list)  # [(frame_num, gray_160x90), ...]
    scanner: Any = None                         # FrameScanner 引用（黑边检测用）
    thresholds: dict = field(default_factory=dict)  # 当前预设的阈值
    performance: dict = field(default_factory=dict)  # 性能设置


class BaseDetector(abc.ABC):
    """检测器基类 — 所有 QC 检测项必须实现此接口。"""

    # 子类必须覆盖：检测项的唯一标识键（对应 result dict 中的 key）
    key: str = ""

    # 子类必须覆盖：人类可读名称
    name: str = ""

    @abc.abstractmethod
    def detect(self, ctx: DetectionContext) -> dict:
        """执行检测，返回结果 dict。

        Returns:
            dict: 检测结果，结构由各检测器自定义。
                  必须包含至少一个布尔值或列表字段供 UI 判定。
        """
        ...

    def __repr__(self):
        return f"<{self.__class__.__name__} key={self.key!r}>"


class DetectorRegistry:
    """检测器注册表 — 管理所有已注册的检测器实例。

    用法:
        registry = DetectorRegistry()
        registry.register(BlackFrameDetectorWrapper())
        registry.register(BlackBorderDetectorWrapper())

        for detector in registry.iterate():
            result[detector.key] = detector.detect(ctx)
    """

    def __init__(self):
        self._detectors: list[BaseDetector] = []
        self._by_key: dict[str, BaseDetector] = {}

    def register(self, detector: BaseDetector) -> None:
        """注册一个检测器。同一 key 重复注册会覆盖。"""
        if not detector.key:
            raise ValueError(f"检测器 {detector!r} 未定义 key")
        # 移除同 key 旧实例
        self._detectors = [d for d in self._detectors if d.key != detector.key]
        self._detectors.append(detector)
        self._by_key[detector.key] = detector
        logger.debug(f"已注册检测器: {detector.key} ({detector.name})")

    def iterate(self) -> list[BaseDetector]:
        """按注册顺序返回所有检测器。"""
        return list(self._detectors)
