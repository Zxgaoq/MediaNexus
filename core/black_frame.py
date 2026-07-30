"""
黑帧检测模块
逐帧检测视频中的纯黑画面（平均像素值低于阈值的帧）。
不跳帧、不 seek，确保单帧黑场不遗漏。
支持黑转场识别：通过亮度梯度分析区分有意淡入淡出与内容缺失错误。
"""

import os
import cv2
import numpy as np
import logging

logger = logging.getLogger("VideoQC.BlackFrame")


class BlackFrameDetector:
    """黑帧检测器 — 逐帧扫描，降分辨率提速"""

    # 转场判定：两侧平均亮度步长均低于此值 = 渐变转场
    # 160×90 灰度缩略图均值范围 0~255，25 约等于 10% 的幅度跳变
    _SLOPE_THRESHOLD = 25

    def __init__(self, threshold=10, min_duration=1):
        """
        Args:
            threshold: 平均像素值阈值（0-255），低于此值判定为黑帧
            min_duration: 最少连续黑帧数，少于此数忽略
        """
        self.threshold = threshold
        self.min_duration = min_duration

    def detect(self, video_path, sample_interval=1, timeout=600):
        """
        逐帧检测黑帧

        策略：
        - 视频 <= 5 分钟: 逐帧扫描（不丢任何帧）
        - 视频 > 5 分钟: 每 sample_interval 帧检查一帧（但逐帧读取保证定位准确）

        使用 160x90 缩略图计算均值，速度极快（<0.01ms/帧）。

        Args:
            video_path: 视频文件路径
            sample_interval: 检查间隔帧数（默认1=逐帧）
            timeout: 超时（参考值）

        Returns:
            dict: {has_black_frames, segments, total_black_frames, frames_checked, fps}
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"文件不存在: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频文件: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        duration = total_frames / fps if fps > 0 else 0

        # 长视频自适应降低检查密度
        if duration > 300:  # 5 分钟以上
            sample_interval = 2
        if duration > 1800:  # 30 分钟以上
            sample_interval = 5

        logger.info(
            f"黑帧检测: {os.path.basename(video_path)} "
            f"({duration:.0f}s, {total_frames}f, fps={fps:.1f}, "
            f"阈值={self.threshold}, 检查间隔={sample_interval})"
        )

        black_segments = []
        total_black = 0
        frames_checked = 0
        current_segment = None
        frame_num = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                frame_num += 1

                # 按间隔决定是否检查当前帧
                if frame_num % sample_interval != 0:
                    continue

                frames_checked += 1

                # 降分辨率快速计算均值：160x90 = 14400 像素，比全分辨率快 100+ 倍
                thumb = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_NEAREST)
                gray = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY)
                mean_pixel = float(np.mean(gray))

                if mean_pixel < self.threshold:
                    total_black += 1
                    if current_segment is None:
                        current_segment = {
                            "start_frame": frame_num,
                            "end_frame": frame_num,
                        }
                    else:
                        current_segment["end_frame"] = frame_num
                else:
                    if current_segment is not None:
                        seg = self._finalize_segment(current_segment, fps, sample_interval)
                        if seg:
                            black_segments.append(seg)
                        current_segment = None

        except Exception as e:
            logger.error(f"黑帧检测异常: {e}")
            import traceback; traceback.print_exc()
        finally:
            cap.release()

        # 最后一个片段
        if current_segment is not None:
            seg = self._finalize_segment(current_segment, fps, sample_interval)
            if seg:
                black_segments.append(seg)

        result = {
            "has_black_frames": len(black_segments) > 0,
            "segments": black_segments,
            "total_black_frames": total_black * sample_interval,  # 还原实际数量
            "frames_checked": frames_checked,
            "fps": round(fps, 2),
        }

        logger.info(f"黑帧检测完成: 扫描 {frames_checked} 帧, 发现 {len(black_segments)} 个黑帧段落")
        return result

    def _finalize_segment(self, seg, fps, sample_interval, thumbs_dict=None):
        """完成片段：还原真实帧范围，计算时长和严重程度，检测转场"""
        # 还原真实帧范围（因为用了 sample_interval）
        start_f = max(seg["start_frame"] - sample_interval + 1, 0)
        end_f = seg["end_frame"]
        frame_count = end_f - start_f + sample_interval

        if frame_count < self.min_duration:
            return None

        start_time = round(start_f / fps, 2)
        end_time = round(end_f / fps, 2)
        duration = round(end_time - start_time, 2)

        # 严重程度分级
        if duration >= 2.0:
            severity = "错误"
        elif duration >= 0.5:
            severity = "警告"
        else:
            severity = "高危 人工复核"

        # 转场检测：分析黑段两侧亮度变化趋势
        is_transition = False
        if thumbs_dict is not None:
            is_transition = self._check_transition(
                thumbs_dict, seg["start_frame"], seg["end_frame"]
            )
            if is_transition:
                severity = "转场"

        return {
            "start_frame": start_f,
            "end_frame": end_f,
            "frame_count": frame_count,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "severity": severity,
            "is_transition": is_transition,
        }

    def _check_transition(self, thumbs_dict, start_frame, end_frame):
        """
        检查黑帧段是否为渐变转场（fade to/from black）。

        分析黑段前后各 5 帧的亮度变化趋势，包含边界帧到黑段的亮度跳变：
          - 渐变（转场）：整条亮度曲线平滑过渡，平均步长 < _SLOPE_THRESHOLD
          - 骤变（错误）：亮度在某处突然跳变，平均步长 >= _SLOPE_THRESHOLD

        只要有一侧呈现渐变特征即判定为转场（兼容视频开头淡入/结尾淡出）。

        Args:
            thumbs_dict: {frame_num: gray_thumb} 映射
            start_frame: 黑段起始帧号
            end_frame: 黑段结束帧号

        Returns:
            bool: True = 渐变转场, False = 非转场或无法判定
        """
        # 黑段内部的代表亮度（取首帧，应为 < threshold 的值）
        black_brightness = 0.0
        if start_frame in thumbs_dict:
            black_brightness = float(np.mean(thumbs_dict[start_frame]))

        # 取黑段前 5 帧（由远及近排列）
        entry_frames = []
        for i in range(1, 6):
            fn = start_frame - i
            if fn in thumbs_dict:
                entry_frames.insert(0, fn)

        # 取黑段后 5 帧（由近及远排列）
        exit_frames = []
        for i in range(1, 6):
            fn = end_frame + i
            if fn in thumbs_dict:
                exit_frames.append(fn)

        # 两侧都无上下文 → 无法判定
        if not entry_frames and not exit_frames:
            return False

        entry_gradual = self._is_gradual_with_boundary(
            entry_frames, thumbs_dict, black_brightness, side='entry'
        )
        exit_gradual = self._is_gradual_with_boundary(
            exit_frames, thumbs_dict, black_brightness, side='exit'
        )

        # 一侧渐变即视为转场（兼容视频开头淡入/结尾淡出）
        if entry_frames and exit_frames:
            return entry_gradual and exit_gradual
        elif entry_frames:
            return entry_gradual
        else:
            return exit_gradual

    def _is_gradual_with_boundary(self, frame_list, thumbs_dict, black_brightness, side):
        """
        判断帧序列的亮度变化是否为渐变，包含边界到黑段的亮度跳变。

        双重条件：
          1. 平均步长 < _SLOPE_THRESHOLD（整体变化幅度小）
          2. 方向占比 >= 0.6（多数步朝预期方向变化）
             - entry（fade-out）：亮度应逐步递减 → 黑段
             - exit（fade-in）：黑段 → 亮度应逐步递增

        防止暗场景中随机亮度波动被误判为渐变转场。
        """
        if len(frame_list) == 0:
            return True  # 无帧视为渐变（不阻断另一侧的判定）

        brightnesses = [float(np.mean(thumbs_dict[fn])) for fn in frame_list]

        # 加入黑段边界亮度，形成完整亮度链
        if side == 'entry':
            # entry: [...context_frames, black]
            brightnesses.append(black_brightness)
        else:
            # exit: [black, ...context_frames]
            brightnesses.insert(0, black_brightness)

        if len(brightnesses) < 2:
            return True

        diffs = [brightnesses[i + 1] - brightnesses[i]
                 for i in range(len(brightnesses) - 1)]
        avg_slope = sum(abs(d) for d in diffs) / len(diffs)

        # 条件 1: 平均步长不超过阈值
        if avg_slope >= self._SLOPE_THRESHOLD:
            return False

        # 条件 2: 方向占比 — 多数步应朝预期方向变化
        if side == 'entry':
            # fade-out: 亮度应逐步递减（diff < 0）
            correct_direction = sum(1 for d in diffs if d < 0)
        else:
            # fade-in: 亮度应逐步递增（diff > 0）
            correct_direction = sum(1 for d in diffs if d > 0)

        direction_ratio = correct_direction / len(diffs)
        return direction_ratio >= 0.6

    def detect_from_thumbs(self, thumbs, fps):
        """
        从预加载缩略图列表检测黑帧（纯内存操作）。

        Args:
            thumbs: [(frame_num, gray_thumb_160x90), ...] — 由 FrameScanner 预提取
            fps: 帧率

        Returns:
            dict: 同 detect() 返回值
        """
        n = len(thumbs)
        black_segments = []
        total_black = 0
        current_segment = None

        # 构建帧号→缩略图映射（供转场检测使用）
        thumbs_dict = {fn: gray for fn, gray in thumbs}

        for frame_num, gray in thumbs:
            mean_pixel = float(np.mean(gray))

            if mean_pixel < self.threshold:
                total_black += 1
                if current_segment is None:
                    current_segment = {"start_frame": frame_num, "end_frame": frame_num}
                else:
                    current_segment["end_frame"] = frame_num
            else:
                if current_segment is not None:
                    seg = self._finalize_segment(current_segment, fps, 1, thumbs_dict)
                    if seg:
                        black_segments.append(seg)
                    current_segment = None

        if current_segment is not None:
            seg = self._finalize_segment(current_segment, fps, 1, thumbs_dict)
            if seg:
                black_segments.append(seg)

        return {
            "has_black_frames": len(black_segments) > 0,
            "segments": black_segments,
            "total_black_frames": total_black,
            "frames_checked": n,
            "fps": round(fps, 2),
        }
