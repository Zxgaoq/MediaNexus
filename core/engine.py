"""
主检测引擎
统一调度所有检测模块，提供批量检测接口。
支持多线程并发检测。
v2: 单次解码扫描引擎 — 三个视觉检测器共享一次视频解码
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
import logging

from core.video_probe import VideoProbe
from core.frame_scanner import FrameScanner
from core.black_border import BlackBorderDetector
from core.silence_detect import SilenceDetector
from core.consistency import ConsistencyChecker
from core.adapters import create_default_registry
from core.base_detector import DetectionContext
from utils.config import ConfigManager, DEFAULT_THRESHOLDS

logger = logging.getLogger("VideoQC.Engine")


class DetectionEngine:
    """视频质检主引擎"""

    def __init__(self):
        self.config = ConfigManager()
        self._probe = VideoProbe()
        self._cancel_flag = threading.Event()
        self._progress_callback = None
        self._log_callback = None
        self._complete_callback = None
        self._registry = create_default_registry()

    def set_progress_callback(self, callback):
        """设置进度回调函数 callback(percent, message)"""
        self._progress_callback = callback

    def set_log_callback(self, callback):
        """设置日志回调函数 callback(message)"""
        self._log_callback = callback

    def set_complete_callback(self, callback):
        """设置完成回调函数 callback()"""
        self._complete_callback = callback

    def cancel(self):
        """取消当前检测任务"""
        self._cancel_flag.set()
        self._log("⚠ 检测任务已请求取消")

    def _log(self, message):
        """内部日志"""
        logger.info(message)
        if self._log_callback:
            self._log_callback(message)

    def _progress(self, percent, message=""):
        """进度更新"""
        if self._progress_callback:
            self._progress_callback(percent, message)

    def analyze_file(self, filepath, fps=None):
        """
        对单个文件执行完整检测流程（并行优化版本 v3）

        ── 调度优化（ADR-008）──
        1. FFprobe 与 FrameScanner 并行启动（两者读同一文件但互不依赖）
        2. 静音检测异步启动，与视觉检测管线并行（只需文件路径，不依赖缩略图）
        3. FrameScanner 自行从 OpenCV 获取时长并计算 sample_interval，
           解除对 FFprobe duration 的前置依赖

        ── 视觉检测管线（共享一次解码，不变）──
        1. FrameScanner 打开视频一次 → 提取缩略图 + 在线运行黑边检测
        2. BlackFrameDetector.detect_from_thumbs() → 纯内存操作
        3. BlackBorderAdapter → 从 scanner 提取预计算结果

        Args:
            filepath: 视频文件路径
            fps: 帧率（可选）
        """
        thresholds = self.config.thresholds
        perf = self.config.performance

        bb_cfg = thresholds.get("black_border", {})
        bb_defaults = DEFAULT_THRESHOLDS["black_border"]

        result = {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "metadata": None,
            "black_frame": None,
            "flash_frame": None,
            "black_border": None,
            "silence": None,
            "errors": [],
            "overall_status": "pending",
        }

        try:
            # ── 1. 构造黑边检测器 ──
            bb_detector = BlackBorderDetector(
                cliff_gradient_min=bb_cfg.get("cliff_gradient_min", bb_defaults["cliff_gradient_min"]),
                border_mean_max=bb_cfg.get("border_mean_max", bb_defaults["border_mean_max"]),
                border_std_max=bb_cfg.get("border_std_max", bb_defaults["border_std_max"]),
                contrast_ratio_min=bb_cfg.get("contrast_ratio_min", bb_defaults["contrast_ratio_min"]),
                min_border_px=bb_cfg.get("min_border_px", bb_defaults["min_border_px"]),
                mode_ratio_min=bb_cfg.get("mode_ratio_min", bb_defaults["mode_ratio_min"]),
            )

            # ── 2. FFprobe 与 FrameScanner 并行（ADR-008）──
            # FFprobe 提供富元数据（编码、色彩空间、HDR 等），
            # FrameScanner 始终以 thumbs_interval=1 逐帧提取缩略图（保证不丢帧），
            # 两者互不依赖，可同时启动。
            scanner = FrameScanner(filepath)

            with ThreadPoolExecutor(max_workers=2) as init_pool:
                probe_future = init_pool.submit(self._probe.probe, filepath)
                scan_future = init_pool.submit(
                    scanner.scan,
                    black_border_detector=bb_detector,
                    sample_interval=None,  # 黑边采样间隔由 scanner 根据 OpenCV 时长自动计算
                    thumbs_interval=1,     # 始终逐帧提取缩略图，后续再按需降采样
                )

                # 等待 FFprobe 完成
                metadata = probe_future.result()
                result["metadata"] = metadata

                if self._cancel_flag.is_set():
                    result["overall_status"] = "cancelled"
                    return result

                # 等待 FrameScanner 完成
                scan_future.result()

            # ── 3. 用 FFprobe 精确时长计算 sample_interval，按需降采样 ──
            if metadata.get("video") and metadata["video"].get("fps"):
                actual_fps = metadata["video"]["fps"]
            else:
                actual_fps = scanner.fps or fps or 25.0

            # 使用 FFprobe 的精确 duration（而非 OpenCV 估算值）来决定采样间隔
            ffprobe_duration = metadata.get("duration") or scanner.duration
            if ffprobe_duration <= 300:
                sample_interval = 1
            elif ffprobe_duration <= 1800:
                sample_interval = 2
            else:
                sample_interval = 3

            if ffprobe_duration > perf.get("max_duration_for_full_scan", 600):
                self._log(f"⚠ 视频过长 ({ffprobe_duration:.0f}s)，部分检测将采用采样模式")

            # 如果 sample_interval > 1，对全量缩略图做降采样（每 N 帧取 1 帧）
            if sample_interval > 1 and scanner.thumbs:
                scanner.thumbs = scanner.thumbs[::sample_interval]

            # ── 4. 静音检测异步启动（与视觉检测并行，ADR-008）──
            sd_cfg = thresholds.get("silence", {})
            sd_defaults = DEFAULT_THRESHOLDS["silence"]
            _silence_detector = SilenceDetector(
                rms_threshold=sd_cfg.get("rms_threshold", sd_defaults["rms_threshold"]),
                min_duration_ignore=sd_cfg.get("min_duration_ignore", sd_defaults["min_duration_ignore"]),
                min_duration_warn=sd_cfg.get("min_duration_warn", sd_defaults["min_duration_warn"]),
                min_duration_error=sd_cfg.get("min_duration_error", sd_defaults["min_duration_error"]),
            )
            silence_executor = ThreadPoolExecutor(max_workers=1)
            silence_future = silence_executor.submit(_silence_detector.detect, filepath)

            # ── 5. 通过注册表驱动视觉检测器（跳过静音，已在后台运行）──
            ctx = DetectionContext(
                filepath=filepath,
                metadata=metadata,
                fps=actual_fps,
                thumbs=scanner.thumbs,
                scanner=scanner,
                thresholds=thresholds,
                performance=perf,
            )

            for detector in self._registry.iterate():
                if detector.key == "silence":
                    continue  # 静音检测已在后台并行运行
                if self._cancel_flag.is_set():
                    result["overall_status"] = "cancelled"
                    silence_future.cancel()
                    silence_executor.shutdown(wait=False)
                    return result
                try:
                    result[detector.key] = detector.detect(ctx)
                except Exception as e:
                    logger.warning(f"检测器 {detector.key} 异常: {e}")
                    result[detector.key] = {"error": str(e)}

            # ── 6. 收集静音检测结果 ──
            try:
                result["silence"] = silence_future.result(timeout=600)
            except Exception as e:
                logger.warning(f"静音检测异常: {e}")
                result["silence"] = {"error": str(e)}
            finally:
                silence_executor.shutdown(wait=False)

            # ── 7. 综合判定 ──
            result["overall_status"] = self._determine_overall(result)

        except FileNotFoundError as e:
            result["errors"].append(f"文件不存在: {e}")
            result["overall_status"] = "error"
        except TimeoutError as e:
            result["errors"].append(f"处理超时: {e}")
            result["overall_status"] = "error"
        except Exception as e:
            result["errors"].append(f"检测异常: {e}")
            result["overall_status"] = "error"
            logger.exception(f"检测失败: {filepath}")

        return result

    def _determine_overall(self, result):
        """综合判定单个文件的检测结果"""
        has_error = False
        has_warning = False

        # 黑帧检查
        bf = result.get("black_frame", {})
        if bf:
            for seg in bf.get("segments", []):
                if seg.get("severity") == "错误":
                    has_error = True
                elif seg.get("severity") == "警告":
                    has_warning = True

        # 黑边检查
        bb = result.get("black_border", {})
        if bb and bb.get("has_black_border"):
            has_warning = True

        # 静音检查
        sd = result.get("silence", {})
        if sd:
            for seg in sd.get("segments", []):
                if seg.get("severity") == "错误":
                    has_error = True
                elif seg.get("severity") == "警告":
                    has_warning = True

        if result.get("errors"):
            return "error"

        if has_error:
            return "fail"
        elif has_warning:
            return "warning"
        return "pass"

    def analyze_batch(self, file_list, fps=None, max_workers=None):
        """
        批量分析多个文件（多线程）

        Args:
            file_list: 文件路径列表
            fps: 帧率（可选）
            max_workers: 最大线程数

        Yields:
            (index, result) 元组
        """
        self._cancel_flag.clear()

        if max_workers is None:
            max_workers = self.config.performance.get("max_threads", 4)

        total = len(file_list)
        self._log(f"开始批量检测: {total} 个文件, 线程数: {max_workers}")
        self._progress(0, f"准备检测 {total} 个文件...")

        results = [None] * total
        # 用于按提交顺序追踪进度（保证进度百分比单调递增，避免跳跃）
        completed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 按提交顺序创建 future，并记录索引映射
            future_to_index = {
                executor.submit(self.analyze_file, f, fps): i
                for i, f in enumerate(file_list)
            }

            # 用 dict 收集已完成的 future，按索引排序后统一更新进度
            pending = set(future_to_index.keys())

            # 已报告的进度百分比（保证不回退）
            last_reported_pct = 0

            # 按完成顺序收集结果，但进度按索引顺序推进
            while pending:
                # 等待任意一个 future 完成
                done_set = set()
                for future in list(pending):
                    if future.done():
                        done_set.add(future)

                if not done_set:
                    # 没有已完成的，短暂等待避免忙等
                    import time as _time
                    _time.sleep(0.05)
                    continue

                for future in done_set:
                    pending.discard(future)
                    index = future_to_index[future]
                    try:
                        result = future.result()
                        results[index] = result
                    except Exception as e:
                        logger.exception(f"文件检测异常 [{index}]: {file_list[index]}")
                        results[index] = {
                            "filepath": file_list[index],
                            "filename": os.path.basename(file_list[index]),
                            "errors": [str(e)],
                            "overall_status": "error",
                        }
                    completed_count += 1
                    latest_name = os.path.basename(
                        (results[index].get("filepath", file_list[index])
                         if results[index] else file_list[index])
                    )

                if self._cancel_flag.is_set():
                    for f in pending:
                        f.cancel()
                    break

                # 进度基于已完成文件数（0-90%），保证单调递增不跳跃
                pct = int(completed_count / total * 90) if total > 0 else 90
                if pct > last_reported_pct:
                    last_reported_pct = pct
                    self._progress(pct, f"已完成 {completed_count}/{total}: {latest_name}")

        # 一致性校验
        self._progress(91, "正在进行一致性校验...")
        valid_results = [r for r in results if r and r.get("metadata")]
        if len(valid_results) >= 2:
            checker = ConsistencyChecker()
            # 传递原始元数据（而非 result 对象）
            probe_list = [r["metadata"] for r in valid_results]
            consistency = checker.check_against_baseline(probe_list)
            # 将一致性结果合并到各文件
            for item in consistency.get("files", []):
                for r in results:
                    if r and r.get("filename") == item.get("filename"):
                        r["consistency"] = item
                        break
            # 保存全局对比矩阵（供 UI 展示）
            for r in results:
                if r:
                    r["_consistency_matrix"] = consistency.get("all_param_values", {})
                    r["_consistency_overall"] = consistency.get("overall_consistent", True)
            status = "一致" if consistency.get("overall_consistent") else f"发现 {sum(1 for f in consistency.get('files', []) if not f.get('is_consistent', True))} 个文件不一致"
            self._log(f"一致性校验完成: {status}")

        self._progress(100, "检测完成！")

        # 触发完成回调（用于提示音等）
        if self._complete_callback:
            self._complete_callback()

        return results

    def validate_environment(self):
        """
        验证运行环境是否就绪

        Returns:
            (bool, str): 环境是否就绪及状态消息
        """
        messages = []

        # 检查 FFmpeg
        from utils.ffmpeg_manager import FFmpegManager
        ffmpeg = FFmpegManager()
        ok, msg = ffmpeg.verify()
        if ok:
            messages.append(f"✅ {msg}")
        else:
            messages.append(f"❌ {msg}")
            messages.append("请将 FFmpeg 二进制文件放入 resources/ffmpeg/ 目录")

        # 检查 OpenCV
        try:
            import cv2
            messages.append(f"✅ OpenCV {cv2.__version__}")
        except ImportError:
            messages.append("❌ OpenCV 未安装")

        # 检查 numpy
        try:
            import numpy as np
            messages.append(f"✅ NumPy {np.__version__}")
        except ImportError:
            messages.append("❌ NumPy 未安装")

        is_ready = all(not m.startswith("❌") for m in messages)
        return is_ready, "\n".join(messages)
