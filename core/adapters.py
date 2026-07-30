# -*- coding: utf-8 -*-
"""
检测器适配器 — 将现有检测器包装为 BaseDetector 统一接口

每个适配器负责：
  1. 从 DetectionContext 中提取所需数据
  2. 调用底层检测器的方法
  3. 返回标准 result dict

这样 DetectionEngine 不再需要知道各检测器的具体接口。
"""
from __future__ import annotations

from .base_detector import BaseDetector, DetectionContext
from .black_frame import BlackFrameDetector
from .black_border import BlackBorderDetector
from .silence_detect import SilenceDetector
from utils.config import DEFAULT_THRESHOLDS


class BlackFrameAdapter(BaseDetector):
    """黑帧检测 — 从内存缩略图检测"""

    key = "black_frame"
    name = "黑帧检测"

    def detect(self, ctx: DetectionContext) -> dict:
        bf_cfg = ctx.thresholds.get("black_frame", {})
        bf_defaults = DEFAULT_THRESHOLDS["black_frame"]
        detector = BlackFrameDetector(
            threshold=bf_cfg.get("mean_pixel_threshold", bf_defaults["mean_pixel_threshold"]),
            min_duration=bf_cfg.get("min_duration", bf_defaults["min_duration"]),
        )
        return detector.detect_from_thumbs(ctx.thumbs, ctx.fps)


class BlackBorderAdapter(BaseDetector):
    """黑边检测 — 从 FrameScanner 已计算的结果中提取

    黑边检测在 FrameScanner.scan() 中在线完成（与缩略图提取共享解码），
    此适配器只负责从 scanner 中提取预计算结果。
    """

    key = "black_border"
    name = "黑边检测"

    def detect(self, ctx: DetectionContext) -> dict:
        # 黑边结果在 FrameScanner.scan() 中已经生成
        if ctx.scanner is not None and hasattr(ctx.scanner, "black_border_result"):
            return ctx.scanner.black_border_result or {}
        return {}


class SilenceAdapter(BaseDetector):
    """静音检测 — 基于音频流分析"""

    key = "silence"
    name = "静音检测"

    def detect(self, ctx: DetectionContext) -> dict:
        sd_cfg = ctx.thresholds.get("silence", {})
        sd_defaults = DEFAULT_THRESHOLDS["silence"]
        detector = SilenceDetector(
            rms_threshold=sd_cfg.get("rms_threshold", sd_defaults["rms_threshold"]),
            min_duration_ignore=sd_cfg.get("min_duration_ignore", sd_defaults["min_duration_ignore"]),
            min_duration_warn=sd_cfg.get("min_duration_warn", sd_defaults["min_duration_warn"]),
            min_duration_error=sd_cfg.get("min_duration_error", sd_defaults["min_duration_error"]),
        )
        return detector.detect(ctx.filepath)


def create_default_registry() -> "DetectorRegistry":
    """创建包含所有内置检测器的注册表。"""
    from .base_detector import DetectorRegistry

    registry = DetectorRegistry()
    registry.register(BlackFrameAdapter())
    registry.register(BlackBorderAdapter())
    registry.register(SilenceAdapter())
    return registry
