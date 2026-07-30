# -*- coding: utf-8 -*-
"""
QC 检测器单元测试
使用合成 numpy 缩略图验证核心检测逻辑，无需真实视频文件。

运行: python -m pytest tests/test_detectors.py -v
"""
import numpy as np
import pytest

from core.black_frame import BlackFrameDetector
from core.black_border import BlackBorderDetector
from MediaNexus.models import Project


# ── 辅助：生成合成缩略图 ──

def make_gray_thumb(value: int, size=(160, 90)) -> np.ndarray:
    """生成均匀灰度缩略图 (H, W)，像素值 = value。"""
    return np.full((size[1], size[0]), value, dtype=np.uint8)


def make_thumbs_sequence(pattern: list[int], start_frame=1) -> list[tuple[int, np.ndarray]]:
    """从像素值列表生成 FrameScanner 格式的 thumbs: [(frame_num, gray_array), ...]"""
    return [(start_frame + i, make_gray_thumb(v)) for i, v in enumerate(pattern)]


# ═══════════════════════════════════════════════════════════
# 黑帧检测器
# ═══════════════════════════════════════════════════════════

class TestBlackFrameDetector:
    """BlackFrameDetector.detect_from_thumbs 测试"""

    def test_no_black_frames(self):
        """全亮帧序列 → 不应检测到黑帧"""
        detector = BlackFrameDetector(threshold=10, min_duration=1)
        thumbs = make_thumbs_sequence([128] * 50)  # 50 帧中等亮度
        result = detector.detect_from_thumbs(thumbs, fps=25.0)

        assert result["has_black_frames"] is False
        assert result["segments"] == []
        assert result["total_black_frames"] == 0
        assert result["frames_checked"] == 50

    def test_continuous_black_segment(self):
        """连续 30 帧黑帧（25fps → 1.2s）→ 应检测到一个警告级段落"""
        detector = BlackFrameDetector(threshold=10, min_duration=1)
        # 10 帧正常 + 30 帧黑 + 10 帧正常
        pattern = [128] * 10 + [2] * 30 + [128] * 10
        thumbs = make_thumbs_sequence(pattern)
        result = detector.detect_from_thumbs(thumbs, fps=25.0)

        assert result["has_black_frames"] is True
        assert len(result["segments"]) == 1
        seg = result["segments"][0]
        # 30 帧 / 25fps = 1.2s → 警告级 (>= 0.5s)
        assert seg["severity"] == "警告"
        assert seg["duration"] >= 1.0

    def test_long_black_segment_is_error(self):
        """连续 60 帧黑帧（25fps → 2.4s）→ 错误级"""
        detector = BlackFrameDetector(threshold=10, min_duration=1)
        pattern = [5] * 10 + [0] * 60 + [200] * 10
        thumbs = make_thumbs_sequence(pattern)
        result = detector.detect_from_thumbs(thumbs, fps=25.0)

        assert result["has_black_frames"] is True
        seg = result["segments"][0]
        assert seg["severity"] == "错误"
        assert seg["duration"] >= 2.0

    def test_short_black_below_min_duration_ignored(self):
        """极短黑帧（低于 min_duration）→ 被过滤"""
        detector = BlackFrameDetector(threshold=10, min_duration=5)
        # 只有 2 帧黑，min_duration=5 应过滤
        pattern = [128] * 20 + [0, 0] + [128] * 20
        thumbs = make_thumbs_sequence(pattern)
        result = detector.detect_from_thumbs(thumbs, fps=25.0)

        assert result["has_black_frames"] is False

    def test_multiple_segments(self):
        """两段分离的黑帧 → 检测到 2 个段落"""
        detector = BlackFrameDetector(threshold=10, min_duration=1)
        pattern = [0] * 20 + [128] * 30 + [0] * 20
        thumbs = make_thumbs_sequence(pattern)
        result = detector.detect_from_thumbs(thumbs, fps=25.0)

        assert result["has_black_frames"] is True
        assert len(result["segments"]) == 2

    def test_threshold_boundary(self):
        """像素值恰好等于阈值 → 不应判定为黑帧（< threshold 才是黑）"""
        detector = BlackFrameDetector(threshold=10, min_duration=1)
        pattern = [10] * 50  # 恰好等于阈值
        thumbs = make_thumbs_sequence(pattern)
        result = detector.detect_from_thumbs(thumbs, fps=25.0)

        assert result["has_black_frames"] is False


# ═══════════════════════════════════════════════════════════
# 黑边检测器
# ═══════════════════════════════════════════════════════════

class TestBlackBorderDetector:
    """BlackBorderDetector 基本接口测试"""

    def test_init_with_defaults(self):
        """默认参数初始化不报错"""
        detector = BlackBorderDetector()
        assert detector is not None

    def test_init_with_custom_params(self):
        """自定义参数初始化"""
        detector = BlackBorderDetector(
            cliff_gradient_min=30,
            border_mean_max=5,
            border_std_max=5,
            contrast_ratio_min=5.0,
            min_border_px=4,
            mode_ratio_min=0.85,
        )
        assert detector is not None

    def test_detect_frame_no_border(self):
        """均匀亮帧 → 不应检测到黑边"""
        detector = BlackBorderDetector()
        # 模拟 960x540 全亮帧
        frame = np.full((540, 960), 128, dtype=np.uint8)
        detector.detect_frame(frame, w=960, h=540)
        # 单帧不足以形成段落，不应崩溃


# ═══════════════════════════════════════════════════════════
# Project 模型
# ═══════════════════════════════════════════════════════════

class TestProjectModel:
    """Project dataclass 校验测试"""

    def test_valid_project(self):
        p = Project(local_name="server/path", name="测试项目", status="matched")
        assert p.display_name == "测试项目"
        assert p.is_matched is True

    def test_display_name_fallback(self):
        """name 为空时 fallback 到路径末段"""
        p = Project(local_name="\\\\NAS\\Projects\\MyShow")
        assert p.display_name == "MyShow"

    def test_empty_local_name_raises(self):
        with pytest.raises(ValueError, match="local_name"):
            Project(local_name="")

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="status"):
            Project(local_name="test", status="invalid_status")

    def test_from_dict_tolerant(self):
        """from_dict 容忍缺失字段"""
        p = Project.from_dict({"local_name": "x"})
        assert p.name == ""
        assert p.status == ""
        assert p.nas_candidates == []

    def test_to_dict_roundtrip(self):
        """to_dict → from_dict 往返一致"""
        original = Project(
            local_name="key", name="显示名",
            local_path="C:/local", status="pending",
            nas_candidates=["\\\\nas\\a", "\\\\nas\\b"],
        )
        restored = Project.from_dict(original.to_dict())
        assert restored == original

    def test_merge_dict(self):
        """merge_dict 增量更新"""
        p = Project(local_name="key", status="pending")
        p.merge_dict({"status": "matched", "confirmed_nas_path": "\\\\nas\\x"})
        assert p.status == "matched"
        assert p.confirmed_nas_path == "\\\\nas\\x"
