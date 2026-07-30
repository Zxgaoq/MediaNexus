"""
黑边检测模块 v3 — 悬崖探测 + 众数稳定性

核心改进（v3）：
- 跨帧稳定性判定从 std/mean 改为众数（mode）+ 出现率
- 真黑边宽度从段开始到结束绝不改变，众数出现率 ≥ 90%
- 暗场景/阴影宽度逐帧变化，众数出现率低，自动过滤
"""
import os
import cv2
import numpy as np
import logging
from collections import Counter

logger = logging.getLogger("VideoQC.BlackBorder")


class BlackBorderDetector:
    """黑边检测器 v3 — 悬崖探测 + 众数稳定性过滤"""

    def __init__(self, cliff_gradient_min=15, border_mean_max=15,
                 border_std_max=8, contrast_ratio_min=3.0,
                 min_border_px=3, mode_ratio_min=0.90,
                 min_segment_frames=3, black_frame_skip_threshold=10):
        """
        Args:
            cliff_gradient_min: 悬崖梯度阈值（亮度剖面中，梯度≥此值视为"悬崖式突变"）
                - 人工黑边过渡：梯度30-200+（0→120一步跨越）
                - 自然暗边缘过渡：梯度5-15（渐进过渡）
                - 默认15：阈值以上=悬崖=人工边界，以下=坡道=自然渐变
            border_mean_max: 候选黑边区域最大均值（0-255）
                - 真实黑边区域均值极低（0-15），有编码噪点也通常≤15
                - 自然暗区域均值较高（15-40）
                - 默认15：容忍编码噪点，排除自然暗区
            border_std_max: 候选黑边区域最大标准差（0-255），单帧检测用
                - 人工黑条内部几乎均匀（Std≈0-5）
                - 自然暗区有纹理/变化（Std≈10-30）
                - 默认8：区分"纯黑条"和"有内容的暗区"
            contrast_ratio_min: 黑边与内容的最低对比度比（相对值）
                - 真实黑边：content_mean / border_mean ≥ 3.0（黑边远暗于内容）
                - 自然暗边缘：对比度比通常1.5-2.5（仅稍暗于内容）
                - 默认3.0：替代旧的绝对阈值center_mean≥50，暗场景也能检测
            min_border_px: 最小报告黑边宽度（原始像素），低于此值忽略
                - 默认3：可检测4-10px的极细黑边（如7px黑边）
            mode_ratio_min: 众数稳定性阈值，段内有值的帧中≥此比例宽度一致才确认
                - 真黑边从段开始到结束宽度不变，众数出现率应接近 1.0
                - 暗场景/阴影的宽度逐帧变化，众数出现率低
                - 默认0.90：90%有值帧宽度一致=真黑边，<90%=暗场景
            min_segment_frames: 最小时间段长度（帧数），短于此值忽略
            black_frame_skip_threshold: 纯黑帧跳过阈值，交给黑帧检测器处理
        """
        self.cliff_gradient_min = cliff_gradient_min
        self.border_mean_max = border_mean_max
        self.border_std_max = border_std_max
        self.contrast_ratio_min = contrast_ratio_min
        self.min_border_px = min_border_px
        self.mode_ratio_min = mode_ratio_min
        self.min_segment_frames = min_segment_frames
        self.black_frame_skip_threshold = black_frame_skip_threshold

    # ── 独立检测入口（向后兼容，内部使用 detect_frame） ──

    def detect(self, video_path, timeout=600):
        """
        独立逐帧扫描检测（向后兼容，v3架构下通常由 FrameScanner 在线检测替代）。
        策略：自适应采样 + 缩放480px + detect_frame 悬崖探测 + _build_segments 众数过滤
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"文件不存在: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开视频: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        duration_sec = total_frames / fps if fps > 0 else 0

        if duration_sec <= 300:
            frame_step = 1
        elif duration_sec <= 900:
            frame_step = 2
        else:
            frame_step = 4

        scale = min(1.0, 480.0 / max(orig_w, orig_h))
        scan_w = max(1, int(orig_w * scale))
        scan_h = max(1, int(orig_h * scale))

        logger.info(
            f"黑边检测(v3): {os.path.basename(video_path)} "
            f"({orig_w}x{orig_h}, {total_frames}f, {fps:.1f}fps, {duration_sec:.0f}s) "
            f"采样步长={frame_step}, 缩放={scan_w}x{scan_h}, scale={scale:.2f}"
        )

        frame_records = []
        frame_num = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                frame_num += 1

                if (frame_num - 1) % frame_step != 0:
                    continue

                if scale < 1.0:
                    frame = cv2.resize(frame, (scan_w, scan_h), interpolation=cv2.INTER_AREA)

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if np.mean(gray) < self.black_frame_skip_threshold:
                    continue

                border = self.detect_frame(gray, scan_w, scan_h, scale)

                if border["has_border"]:
                    frame_records.append((frame_num, border))
        except Exception as e:
            logger.error(f"黑边检测异常: {e}")
        finally:
            cap.release()

        logger.info(f"黑边扫描完成: {frame_num} 帧，{len(frame_records)} 帧有黑边")

        return self._build_segments(frame_records, fps, frame_step, orig_w, orig_h, total_frames)

    # ── 核心算法：单帧悬崖探测 ──

    def detect_frame(self, gray, w, h, scale=1.0):
        """
        单帧黑边检测 — 悬崖探测算法。

        五级流水线：
        1. 亮度剖面提取：从边缘向中心提取1D均值信号
        2. 梯度计算+悬崖定位：找到第一个满足阈值的亮度突变
        3. 区域统计验证：三重条件（绝对暗度+内部方差+对比度）
        4. 自适应暗场景：用相对对比度替代绝对亮度阈值
        5. 像素换算：缩放像素→原始分辨率像素

        Args:
            gray: 缩放后的灰度图 (numpy array)
            w, h: 缩放后的宽高
            scale: 缩放比例 (<1.0 表示已缩放)

        Returns:
            dict: {has_border, top_px, bottom_px, left_px, right_px,
                   valid_ratio, border_type} — 像素值已换算回原始分辨率
        """
        scan_depth_v = max(5, int(h * 0.25))
        scan_depth_h = max(5, int(w * 0.25))

        min_border_scaled = max(2, round(self.min_border_px * scale)) if scale < 1.0 else self.min_border_px

        top_s = self._detect_edge_cliff(gray, 'top', w, h, scan_depth_v, min_border_scaled)
        bottom_s = self._detect_edge_cliff(gray, 'bottom', w, h, scan_depth_v, min_border_scaled)
        left_s = self._detect_edge_cliff(gray, 'left', w, h, scan_depth_h, min_border_scaled)
        right_s = self._detect_edge_cliff(gray, 'right', w, h, scan_depth_h, min_border_scaled)

        if scale < 1.0:
            top_px = round(top_s / scale)
            bottom_px = round(bottom_s / scale)
            left_px = round(left_s / scale)
            right_px = round(right_s / scale)
            orig_w = round(w / scale)
            orig_h = round(h / scale)
        else:
            top_px = top_s
            bottom_px = bottom_s
            left_px = left_s
            right_px = right_s
            orig_w = w
            orig_h = h

        vw = max(1, orig_w - left_px - right_px)
        vh = max(1, orig_h - top_px - bottom_px)
        valid_ratio = round((vw * vh) / (orig_w * orig_h), 4)

        has_border = (top_px >= self.min_border_px or bottom_px >= self.min_border_px or
                      left_px >= self.min_border_px or right_px >= self.min_border_px)

        parts = []
        if top_px >= self.min_border_px and bottom_px >= self.min_border_px:
            parts.append("上下")
        elif top_px >= self.min_border_px:
            parts.append("上")
        elif bottom_px >= self.min_border_px:
            parts.append("下")
        if left_px >= self.min_border_px and right_px >= self.min_border_px:
            parts.append("左右")
        elif left_px >= self.min_border_px:
            parts.append("左")
        elif right_px >= self.min_border_px:
            parts.append("右")
        border_type = "+".join(parts) if parts else ""

        return {
            "has_border": has_border,
            "top_px": top_px,
            "bottom_px": bottom_px,
            "left_px": left_px,
            "right_px": right_px,
            "valid_ratio": valid_ratio,
            "border_type": border_type,
        }

    def _detect_edge_cliff(self, gray, direction, w, h, scan_depth, min_border_scaled):
        """
        单边悬崖探测：亮度剖面 → 梯度 → 遍历所有悬崖候选者 → 三重验证 → 取首个通过者。

        核心逻辑：
        - 人工黑边：平坦极暗区 → 悬崖式突变 → 平坦亮区（梯度30-200+）
        - 自然暗边缘：渐进过渡（梯度5-15），无悬崖
        - 暗场景全局暗：无悬崖，梯度普遍很小

        改进：不再只取第一个悬崖候选者，而是遍历所有候选者做三重验证，
        取首个通过验证的悬崖。这解决了噪声产生的第一悬崖验证失败后，
        真正的边界悬崖被忽略的问题。

        Returns: 黑边宽度（缩放像素），0表示无黑边
        """
        if direction == 'top':
            profile = np.mean(gray[:scan_depth, :], axis=1)
        elif direction == 'bottom':
            profile = np.mean(gray[h - scan_depth:, :], axis=1)
            profile = profile[::-1]
        elif direction == 'left':
            profile = np.mean(gray[:, :scan_depth], axis=0)
        elif direction == 'right':
            profile = np.mean(gray[:, w - scan_depth:], axis=0)
            profile = profile[::-1]

        gradient = np.diff(profile)
        cliff_candidates = np.where(gradient >= self.cliff_gradient_min)[0]

        if len(cliff_candidates) == 0:
            return 0

        for cliff_pos_raw in cliff_candidates:
            cliff_pos = int(cliff_pos_raw)
            cliff_mag = float(gradient[cliff_pos])

            if cliff_pos < min_border_scaled - 1:
                continue

            delta = min(20, scan_depth - cliff_pos - 2)
            if delta < 5:
                continue

            if direction == 'top':
                region_a = gray[:cliff_pos + 1, :]
                region_b = gray[cliff_pos + 1:cliff_pos + 1 + delta, :]
            elif direction == 'bottom':
                region_a = gray[h - cliff_pos - 1:, :]
                region_b = gray[h - cliff_pos - 1 - delta:h - cliff_pos - 1, :]
            elif direction == 'left':
                region_a = gray[:, :cliff_pos + 1]
                region_b = gray[:, cliff_pos + 1:cliff_pos + 1 + delta]
            elif direction == 'right':
                region_a = gray[:, w - cliff_pos - 1:]
                region_b = gray[:, w - cliff_pos - 1 - delta:w - cliff_pos - 1]

            mean_a = float(np.mean(region_a))
            std_a = float(np.std(region_a))
            mean_b = float(np.mean(region_b))
            contrast = mean_b / max(mean_a, 1.0)

            if mean_a > self.border_mean_max:
                logger.debug(
                    f"  {direction}: cliff@{cliff_pos} mag={cliff_mag:.0f} "
                    f"SKIP mean_a={mean_a:.1f}>{self.border_mean_max}"
                )
                continue

            if std_a > self.border_std_max:
                logger.debug(
                    f"  {direction}: cliff@{cliff_pos} mag={cliff_mag:.0f} "
                    f"SKIP std_a={std_a:.1f}>{self.border_std_max}"
                )
                continue

            if contrast < self.contrast_ratio_min:
                logger.debug(
                    f"  {direction}: cliff@{cliff_pos} mag={cliff_mag:.0f} "
                    f"SKIP contrast={contrast:.1f}<{self.contrast_ratio_min}"
                )
                continue

            logger.debug(
                f"  {direction}: cliff@{cliff_pos} mag={cliff_mag:.0f} "
                f"CONFIRM mean={mean_a:.1f} std={std_a:.1f} contrast={contrast:.1f}"
            )
            return cliff_pos + 1

        logger.debug(f"  {direction}: all {len(cliff_candidates)} cliffs rejected")
        return 0

    # ── 时间段合并 + 众数稳定性过滤 ──

    def _build_segments(self, frame_records, fps, frame_step, orig_w, orig_h, total_frames):
        """
        将连续有黑边的帧合并为时间段，并过滤宽度不稳定的边缘。

        众数稳定性逻辑（核心洞察：真黑边宽度从段开始到结束绝不改变）：
        - 真黑边（Letterbox/Pillarbox）：段内每帧宽度是同一个常数
          → 非零宽度众数出现率接近 1.0
        - 暗场景/阴影：宽度逐帧变化，无稳定众数
          → 众数出现率低，判定为不稳定
        - 仅报告众数稳定的边缘，过滤不稳定的边缘（暗场景）
        - 段内至少一个边缘稳定才保留该段
        """
        if not frame_records:
            return {
                "has_black_border": False,
                "segments": [],
                "total_border_frames": 0,
                "frames_checked": len(frame_records),
                "avg_valid_ratio": 1.0,
                "border_type": "无黑边",
                "details": {},
                "max_border_px": {},
                "resolution": f"{orig_w}x{orig_h}",
                "total_frames": total_frames,
                "fps": round(fps, 2),
            }

        # ── 合并连续帧为段 ──
        base_gap = frame_step * 3
        time_gap = int(fps * 2.0) if fps > 0 else 50
        gap_tolerance = max(base_gap, time_gap)

        logger.debug(
            f"  段合并: frame_step={frame_step}, gap_tolerance={gap_tolerance} "
            f"(base={base_gap}, time_gap={time_gap})"
        )

        segments_raw = []
        current_seg = [frame_records[0]]

        for i in range(1, len(frame_records)):
            prev_frame = frame_records[i - 1][0]
            curr_frame = frame_records[i][0]
            if curr_frame - prev_frame <= gap_tolerance:
                current_seg.append(frame_records[i])
            else:
                segments_raw.append(current_seg)
                current_seg = [frame_records[i]]
        segments_raw.append(current_seg)

        # ── 众数稳定性过滤 + 构建输出 ──
        segments = []
        all_valid_ratios = []
        max_borders = {"top": 0, "bottom": 0, "left": 0, "right": 0}

        for seg in segments_raw:
            seg_frame_count = len(seg)
            actual_frames = (seg[-1][0] - seg[0][0] + 1)
            duration = actual_frames / fps if fps > 0 else 0

            if actual_frames < self.min_segment_frames:
                continue

            start_frame = seg[0][0]
            end_frame = seg[-1][0]
            start_time = start_frame / fps if fps > 0 else 0
            end_time = end_frame / fps if fps > 0 else 0

            # ── 众数稳定性分析 ──
            edges_data = {
                'top': [r[1]["top_px"] for r in seg],
                'bottom': [r[1]["bottom_px"] for r in seg],
                'left': [r[1]["left_px"] for r in seg],
                'right': [r[1]["right_px"] for r in seg],
            }

            stable_edges = {}
            for edge_name, widths in edges_data.items():
                # 收集该边在段内每帧的检测宽度（非零值）
                nonzero = [w for w in widths if w >= self.min_border_px]

                if len(nonzero) == 0:
                    # 该边在段内所有帧都无黑边
                    stable_edges[edge_name] = {
                        'mode': 0,
                        'mode_ratio': 0.0,
                        'stable': False,
                    }
                    continue

                # 计算众数（出现次数最多的宽度值）
                counter = Counter(nonzero)
                width_mode, count_mode = counter.most_common(1)[0]

                # mode_ratio：分母是该边有值帧数（非零帧数）
                # 这样纯黑帧跳过不影响 mode_ratio
                mode_ratio = count_mode / len(nonzero)

                is_stable = (mode_ratio >= self.mode_ratio_min)

                stable_edges[edge_name] = {
                    'mode': width_mode,
                    'mode_ratio': round(mode_ratio, 3),
                    'count': count_mode,
                    'total_nonzero': len(nonzero),
                    'stable': is_stable,
                }

                logger.debug(
                    f"  边={edge_name} 众数={width_mode}px "
                    f"出现={count_mode}/{len(nonzero)}={mode_ratio:.1%} "
                    f"稳定={is_stable}"
                )

            # 如果没有任何边缘是稳定的，丢弃这个段（是暗场景）
            has_stable_edge = any(e['stable'] for e in stable_edges.values())
            if not has_stable_edge:
                logger.debug(
                    f"  段 {start_time:.1f}s-{end_time:.1f}s: 无稳定边缘（暗场景），过滤"
                )
                continue

            # 使用众数作为报告值
            avg_top = stable_edges['top']['mode'] if stable_edges['top']['stable'] else 0
            avg_bot = stable_edges['bottom']['mode'] if stable_edges['bottom']['stable'] else 0
            avg_lef = stable_edges['left']['mode'] if stable_edges['left']['stable'] else 0
            avg_rig = stable_edges['right']['mode'] if stable_edges['right']['stable'] else 0

            # max_border_px 仍取段内最大值
            max_top = int(np.max(edges_data['top'])) if any(w > 0 for w in edges_data['top']) else 0
            max_bot = int(np.max(edges_data['bottom'])) if any(w > 0 for w in edges_data['bottom']) else 0
            max_lef = int(np.max(edges_data['left'])) if any(w > 0 for w in edges_data['left']) else 0
            max_rig = int(np.max(edges_data['right'])) if any(w > 0 for w in edges_data['right']) else 0

            max_borders["top"] = max(max_borders["top"], max_top)
            max_borders["bottom"] = max(max_borders["bottom"], max_bot)
            max_borders["left"] = max(max_borders["left"], max_lef)
            max_borders["right"] = max(max_borders["right"], max_rig)

            vw = max(1, orig_w - avg_lef - avg_rig)
            vh = max(1, orig_h - avg_top - avg_bot)
            avg_valid = round((vw * vh) / (orig_w * orig_h), 4)
            all_valid_ratios.append(avg_valid)

            parts = []
            if stable_edges['top']['stable'] and stable_edges['bottom']['stable']:
                parts.append("上下")
            elif stable_edges['top']['stable']:
                parts.append("上")
            elif stable_edges['bottom']['stable']:
                parts.append("下")
            if stable_edges['left']['stable'] and stable_edges['right']['stable']:
                parts.append("左右")
            elif stable_edges['left']['stable']:
                parts.append("左")
            elif stable_edges['right']['stable']:
                parts.append("右")
            main_type = "+".join(parts) if parts else ""

            if duration >= 3.0:
                severity = "错误"
            elif duration >= 1.0:
                severity = "警告"
            else:
                severity = "提示"

            segments.append({
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_time": round(start_time, 2),
                "end_time": round(end_time, 2),
                "duration": round(duration, 2),
                "severity": severity,
                "border_type": main_type,
                "avg_top_px": avg_top,
                "avg_bottom_px": avg_bot,
                "avg_left_px": avg_lef,
                "avg_right_px": avg_rig,
                "max_top_px": max_top,
                "max_bottom_px": max_bot,
                "max_left_px": max_lef,
                "max_right_px": max_rig,
                "avg_valid_ratio": avg_valid,
                "frame_count": seg_frame_count,
            })

        # ── 后合并：同类型且宽度一致的相邻段合并 ──
        merge_gap_sec = 5.0
        merged_segments = []
        for seg in segments:
            if not merged_segments:
                merged_segments.append(seg)
                continue
            prev = merged_segments[-1]
            gap_sec = seg["start_time"] - prev["end_time"]
            same_type = (prev["border_type"] == seg["border_type"])
            width_compatible = True
            for edge in ["top_px", "bottom_px", "left_px", "right_px"]:
                prev_w = prev.get(f"avg_{edge}", 0)
                curr_w = seg.get(f"avg_{edge}", 0)
                if prev_w > 0 and curr_w > 0:
                    if abs(curr_w - prev_w) / max(prev_w, curr_w) > 0.05:
                        width_compatible = False
                        break
            if gap_sec <= merge_gap_sec and same_type and width_compatible:
                prev["end_frame"] = seg["end_frame"]
                prev["end_time"] = seg["end_time"]
                prev["duration"] = round(seg["end_time"] - prev["start_time"], 2)
                prev["frame_count"] += seg["frame_count"]
                for edge in ["top_px", "bottom_px", "left_px", "right_px"]:
                    avg_key = f"avg_{edge}"
                    max_key = f"max_{edge}"
                    prev[avg_key] = round(
                        (prev[avg_key] * prev.get("_merge_weight", 1) + seg[avg_key] * seg["frame_count"])
                        / (prev.get("_merge_weight", 1) + seg["frame_count"]), 1
                    )
                    prev[max_key] = max(prev[max_key], seg[max_key])
                prev["_merge_weight"] = prev.get("_merge_weight", 1) + seg["frame_count"]
                if prev["duration"] >= 3.0:
                    prev["severity"] = "错误"
                elif prev["duration"] >= 1.0:
                    prev["severity"] = "警告"
                else:
                    prev["severity"] = "提示"
                vw = max(1, orig_w - prev["avg_left_px"] - prev["avg_right_px"])
                vh = max(1, orig_h - prev["avg_top_px"] - prev["avg_bottom_px"])
                prev["avg_valid_ratio"] = round((vw * vh) / (orig_w * orig_h), 4)
            else:
                merged_segments.append(seg)

        for seg in merged_segments:
            seg.pop("_merge_weight", None)

        segments = merged_segments
        total_border_frames = sum(s["frame_count"] for s in segments)
        overall_valid = float(np.mean(all_valid_ratios)) if all_valid_ratios else 1.0
        has_border = len(segments) > 0

        if segments:
            all_types = [s["border_type"] for s in segments]
            type_counter = Counter(all_types)
            border_type = "+".join([t for t, _ in type_counter.most_common()])
        else:
            border_type = "无黑边"

        logger.info(
            f"黑边结果(v3): {len(segments)} 个时间段, "
            f"共 {total_border_frames} 帧, "
            f"valid={overall_valid:.1%}, max={max_borders}"
        )
        for s in segments:
            logger.info(
                f"  [{s['severity']}] {s['start_time']:.1f}s-{s['end_time']:.1f}s "
                f"({s['duration']:.1f}s) {s['border_type']} "
                f"T={s['avg_top_px']}px B={s['avg_bottom_px']}px "
                f"L={s['avg_left_px']}px R={s['avg_right_px']}px"
            )

        return {
            "has_black_border": has_border,
            "segments": segments,
            "total_border_frames": total_border_frames,
            "frames_checked": len(frame_records),
            "avg_valid_ratio": round(overall_valid, 4),
            "border_type": border_type,
            "details": {
                "top_px": round(float(np.mean([s["avg_top_px"] for s in segments])), 1) if segments else 0,
                "bottom_px": round(float(np.mean([s["avg_bottom_px"] for s in segments])), 1) if segments else 0,
                "left_px": round(float(np.mean([s["avg_left_px"] for s in segments])), 1) if segments else 0,
                "right_px": round(float(np.mean([s["avg_right_px"] for s in segments])), 1) if segments else 0,
            },
            "max_border_px": max_borders,
            "resolution": f"{orig_w}x{orig_h}",
            "total_frames": total_frames,
            "fps": round(fps, 2),
        }
