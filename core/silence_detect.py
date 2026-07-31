"""
静音检测模块
基于 RMS 能量阈值检测音频中的静音片段。
"""

import os
import subprocess
import platform
import numpy as np
import logging
from utils.ffmpeg_manager import FFmpegManager

logger = logging.getLogger("VideoQC.SilenceDetect")

# 尝试导入 librosa，如果不可用则使用 FFmpeg 替代方案
try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    logger.warning("librosa 未安装，将使用 FFmpeg silence detect 滤镜")


class SilenceDetector:
    """静音检测器"""

    def __init__(self, rms_threshold=0.01, min_duration_ignore=0.5,
                 min_duration_warn=2.0, min_duration_error=5.0):
        """
        Args:
            rms_threshold: RMS 能量阈值，低于此值判定为静音
            min_duration_ignore: 忽略短于此秒数的静音
            min_duration_warn: 警告级别静音时长阈值（秒）
            min_duration_error: 错误级别静音时长阈值（秒）
        """
        self.rms_threshold = rms_threshold
        self.min_duration_ignore = min_duration_ignore
        self.min_duration_warn = min_duration_warn
        self.min_duration_error = min_duration_error
        self._ffmpeg = FFmpegManager()

    def detect(self, video_path, timeout=300):
        """
        检测音频静音片段

        Args:
            video_path: 视频文件路径
            timeout: 超时

        Returns:
            dict: {
                "has_silence": bool,
                "segments": [{"start": float, "end": float, "duration": float, "severity": str}, ...],
                "total_silence_duration": float,
            }
        """
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"文件不存在: {video_path}")

        logger.info(f"静音检测开始: {video_path}")

        segments = []

        # 首先检查是否有音频流
        has_audio = self._has_audio_stream(video_path)
        if not has_audio:
            logger.info(f"文件无音频流: {video_path}")
            return {
                "has_silence": False,
                "segments": [],
                "total_silence_duration": 0,
                "no_audio": True,
            }

        try:
            # 优先使用 FFmpeg silencedetect（流式处理，比 librosa 提取 WAV 快 3-5×）
            segments = self._detect_with_ffmpeg(video_path)
        except Exception as e:
            logger.warning(f"FFmpeg 静音检测失败: {e}，尝试 librosa")
            try:
                if HAS_LIBROSA:
                    segments = self._detect_with_librosa(video_path)
                else:
                    logger.error("librosa 不可用，静音检测完全失败")
                    return {
                        "has_silence": False,
                        "segments": [],
                        "total_silence_duration": 0,
                        "error": str(e),
                    }
            except Exception as e2:
                logger.error(f"librosa 静音检测也失败: {e2}")
                return {
                    "has_silence": False,
                    "segments": [],
                    "total_silence_duration": 0,
                    "error": str(e),
                }

        # 分级与过滤
        filtered = []
        total_silence = 0
        for seg in segments:
            duration = round(seg["end"] - seg["start"], 2)
            if duration < self.min_duration_ignore:
                continue

            if duration >= self.min_duration_error:
                severity = "错误"
            elif duration >= self.min_duration_warn:
                severity = "警告"
            else:
                severity = "忽略" if duration < self.min_duration_ignore else "提示"

            if severity != "忽略":
                filtered.append({
                    "start": round(seg["start"], 2),
                    "end": round(seg["end"], 2),
                    "duration": duration,
                    "severity": severity,
                })
                total_silence += duration

        result = {
            "has_silence": len(filtered) > 0,
            "segments": filtered,
            "total_silence_duration": round(total_silence, 2),
            "no_audio": False,
        }

        logger.info(f"静音检测完成: 发现 {len(filtered)} 个静音段落, 总时长={total_silence:.1f}s")
        return result

    def _has_audio_stream(self, video_path):
        """检查是否有音频流"""
        probe_cmd = [
            self._ffmpeg.get_ffprobe_path(),
            "-v", "quiet",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            video_path
        ]
        kw = dict(capture_output=True, timeout=30, encoding="utf-8", errors="replace")
        if platform.system() == "Windows":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(probe_cmd, **kw)
        stdout = result.stdout or ""
        return "audio" in stdout

    def _detect_with_librosa(self, video_path):
        """
        使用 librosa 进行静音检测

        通过 FFmpeg 提取音频 -> 缓存目录 WAV -> librosa 分析
        临时文件统一存放在 data/cache/audio/ 下，不会散落系统临时目录。
        """
        from utils.storage_manager import StorageManager

        storage = StorageManager()
        # 使用视频文件名的哈希或安全名称作为缓存标识
        import hashlib
        video_key = hashlib.md5(video_path.encode()).hexdigest()[:12]
        tmp_path = storage.get_cache_path("audio", f"{video_key}_extracted.wav")

        try:
            # FFmpeg 提取音频
            extract_cmd = [
                self._ffmpeg.get_ffmpeg_path(),
                "-i", video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                "-y", tmp_path
            ]
            kw = dict(capture_output=True, timeout=120, encoding="utf-8", errors="replace")
            if platform.system() == "Windows":
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.run(extract_cmd, **kw)

            if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) == 0:
                self._safe_remove(tmp_path)
                return []

            # librosa 加载分析
            y, sr = librosa.load(tmp_path, sr=None, mono=True)
            if len(y) == 0:
                self._safe_remove(tmp_path)
                return []

            # 计算 RMS 能量（移动窗口）
            frame_length = 2048
            hop_length = 512
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

            # 时间轴
            times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop_length)

            # 检测静音段
            is_silent = rms < self.rms_threshold
            segments = self._find_continuous_segments(times, is_silent, sr, hop_length)

            # 分析完成后清理临时音频（用户可通过缓存管理统一清理残留）
            self._safe_remove(tmp_path)

            return segments

        except Exception:
            self._safe_remove(tmp_path)
            raise

    def _safe_remove(self, path):
        """安全删除文件，忽略权限等问题"""
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    def _detect_with_ffmpeg(self, video_path):
        """
        使用 FFmpeg silencedetect 滤镜检测静音

        这是降级方案，当 librosa 不可用时使用
        """
        # FFmpeg silencedetect 使用 dB，转换为 dB
        # RMS 阈值到 dB 的粗略映射
        # rms_threshold: 0.01 -> -40dB, 0.005 -> -46dB, 0.02 -> -34dB
        if self.rms_threshold > 0:
            noise_db = max(-60, min(0, 20 * np.log10(self.rms_threshold)))
        else:
            noise_db = -60

        cmd = [
            self._ffmpeg.get_ffmpeg_path(),
            "-i", video_path,
            "-af", f"silencedetect=noise={noise_db}dB:d=0.1",
            "-f", "null",
            "-"
        ]

        kw = dict(capture_output=True, timeout=300, encoding="utf-8", errors="replace")
        if platform.system() == "Windows":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, **kw)

        # 解析输出
        segments = []
        lines = result.stderr.split("\n") if result.stderr else []
        current_start = None

        for line in lines:
            if "silence_start" in line:
                try:
                    current_start = float(line.split("silence_start:")[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
            elif "silence_end" in line and current_start is not None:
                try:
                    end = float(line.split("silence_end:")[1].strip().split()[0])
                    segments.append({"start": current_start, "end": end})
                    current_start = None
                except (ValueError, IndexError):
                    pass

        return segments

    def _find_continuous_segments(self, times, is_silent, sr, hop_length):
        """从布尔数组中提取连续的 True 段"""
        segments = []
        in_segment = False
        start_idx = 0

        for i in range(len(is_silent)):
            if is_silent[i] and not in_segment:
                in_segment = True
                start_idx = i
            elif not is_silent[i] and in_segment:
                in_segment = False
                segments.append({
                    "start": float(times[start_idx]),
                    "end": float(times[min(i, len(times) - 1)]),
                })

        if in_segment:
            segments.append({
                "start": float(times[start_idx]),
                "end": float(times[-1]),
            })

        return segments
