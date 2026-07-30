"""
统一帧扫描器 v2
单次解码视频，同时提取缩略图 + 黑边在线检测（委托 BlackBorderDetector.detect_frame）。
消除三个检测器各自独立解码全帧的冗余开销（~80%总耗时）。
"""
import os
import cv2
import numpy as np
import logging

logger = logging.getLogger("VideoQC.FrameScanner")


class FrameScanner:
    """单次解码扫描器：一次 cap.read() 循环服务所有视觉检测器"""

    def __init__(self, video_path):
        self.video_path = video_path
        self._cap = None

        # 扫描结果
        self.thumbs = []           # [(frame_num, gray_thumb_160x90), ...]
        self.fps = 25.0
        self.total_frames = 0
        self.duration = 0.0
        self.orig_w = 0
        self.orig_h = 0

        # 黑边在线检测结果
        self.black_border_result = None

    def scan(self, black_border_detector=None, sample_interval=None, thumbs_interval=1):
        """
        单次遍历所有帧：
          1. 为黑帧提取 160x90 gray thumb（由 thumbs_interval 控制密度）
          2. 如果提供了 black_border_detector，委托其 detect_frame() 在线检测黑边

        Args:
            black_border_detector: BlackBorderDetector 实例或 None
            sample_interval: 黑边检测采样间隔，None 时根据视频时长自动计算
                             (<=5min→1, <=15min→2, >15min→4)
            thumbs_interval: 缩略图提取间隔（默认1=逐帧提取），
                             engine 可根据 FFprobe 精确时长在事后降采样

        Returns:
            bool: 是否成功
        """
        if not os.path.isfile(self.video_path):
            raise FileNotFoundError(f"文件不存在: {self.video_path}")

        self._cap = cv2.VideoCapture(self.video_path)
        if not self._cap.isOpened():
            raise RuntimeError(f"无法打开视频: {self.video_path}")

        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        self.orig_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        self.orig_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        self.duration = self.total_frames / self.fps if self.fps > 0 else 0

        # 自动计算黑边采样间隔（engine 传 None 时由 scanner 根据时长自行决定）
        if sample_interval is None:
            if self.duration <= 300:
                sample_interval = 1
            elif self.duration <= 900:
                sample_interval = 2
            else:
                sample_interval = 4

        # ── 准备黑边在线检测 ──
        bb_records = []
        bb_frame_step = sample_interval
        bb_scale = 1.0
        bb_scan_w = self.orig_w
        bb_scan_h = self.orig_h
        bb_black_skip = 0

        if black_border_detector is not None:
            # 黑边独立采样步长
            if self.duration <= 300:
                bb_frame_step = 1
            elif self.duration <= 900:
                bb_frame_step = 2
            else:
                bb_frame_step = 4

            # 缩放 960px（兼顾精度与速度，支持检测极细黑边，最小可检测~4px原始宽度）
            bb_scale = min(1.0, 960.0 / max(self.orig_w, self.orig_h))
            bb_scan_w = max(1, int(self.orig_w * bb_scale))
            bb_scan_h = max(1, int(self.orig_h * bb_scale))
            bb_black_skip = black_border_detector.black_frame_skip_threshold

        logger.info(
            f"FrameScanner: {os.path.basename(self.video_path)} "
            f"({self.orig_w}x{self.orig_h}, {self.total_frames}f, {self.duration:.0f}s) "
            f"bb_enabled={black_border_detector is not None}, "
            f"bb_step={bb_frame_step}, bb_scale={bb_scale:.2f}, "
            f"thumbs_interval={thumbs_interval}"
        )

        frame_num = 0

        try:
            while True:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    break
                frame_num += 1

                # ── 黑帧用缩略图（由 thumbs_interval 控制，默认逐帧提取） ──
                if (frame_num - 1) % thumbs_interval == 0:
                    thumb = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_NEAREST)
                    gray = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY)
                    self.thumbs.append((frame_num, gray))

                # ── 黑边在线检测（委托 BlackBorderDetector.detect_frame） ──
                if black_border_detector is not None and (frame_num - 1) % bb_frame_step == 0:
                    # 缩放帧
                    if bb_scale < 1.0:
                        bb_frame = cv2.resize(frame, (bb_scan_w, bb_scan_h), interpolation=cv2.INTER_AREA)
                    else:
                        bb_frame = frame
                    bb_gray = cv2.cvtColor(bb_frame, cv2.COLOR_BGR2GRAY)

                    # 跳过纯黑帧
                    bb_mean = np.mean(bb_gray)
                    if bb_mean < bb_black_skip:
                        continue

                    # 委托 BlackBorderDetector 的 detect_frame 进行悬崖探测
                    border = black_border_detector.detect_frame(
                        bb_gray, bb_scan_w, bb_scan_h, bb_scale
                    )

                    if border["has_border"]:
                        bb_records.append((frame_num, border))

        except Exception as e:
            logger.error(f"FrameScanner 扫描异常: {e}")
            import traceback; traceback.print_exc()
        finally:
            self._cap.release()

        logger.info(
            f"FrameScanner done: {frame_num} frames decoded, "
            f"{len(self.thumbs)} thumbs stored, "
            f"{len(bb_records)} border frames"
        )

        # ── 构建黑边结果（委托 BlackBorderDetector._build_segments + 一致性过滤） ──
        if black_border_detector is not None:
            self.black_border_result = black_border_detector._build_segments(
                bb_records, self.fps, bb_frame_step,
                self.orig_w, self.orig_h, self.total_frames
            )

        return True
