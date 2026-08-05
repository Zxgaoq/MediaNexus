"""
视频元数据探测模块（重写版）
基于 FFprobe 提取完整技术参数，数倍精度提升。
"""
import os
import json
import subprocess
import platform
import logging
from utils.ffmpeg_manager import FFmpegManager

logger = logging.getLogger("MediaNexus.QC.VideoProbe")


class VideoProbe:
    """视频元数据探测器 — 精准版"""

    def __init__(self):
        self._ffmpeg = FFmpegManager()
        self._ffprobe = self._ffmpeg.get_ffprobe_path()

    def probe(self, filepath):
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")
        logger.info(f"正在探测: {filepath}")
        try:
            # Windows 下 text=True 默认用 GBK 编码，遇到非 GBK 字节会 UnicodeDecodeError
            # 必须显式指定 utf-8 + errors='replace' 兼容所有可能的输出
            kw = dict(
                capture_output=True,
                timeout=60,
                encoding="utf-8",
                errors="replace",
            )
            if platform.system() == "Windows":
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run([
                self._ffprobe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-show_chapters",
                filepath
            ], **kw)

            # FFprobe 执行失败（文件损坏/被占用/权限不足等）
            if result.returncode != 0:
                stderr_msg = (result.stderr or "").strip()
                raise RuntimeError(f"FFprobe 执行失败 (exit code {result.returncode}): {stderr_msg}")

            # 某些情况下 stdout 可能为空或 None（如文件被锁、进程被杀）
            raw_text = result.stdout
            if not raw_text or not raw_text.strip():
                raise RuntimeError("FFprobe 未返回任何输出，可能文件被占用或不支持")

            raw = json.loads(raw_text)
            return self._parse(raw, filepath)

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"探测超时 (60s): {filepath}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"FFprobe 输出解析失败: {e}")

    # ─────────────────────── 解析入口 ───────────────────────
    def _parse(self, raw, filepath):
        info = {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "filesize_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
            "filesize_bytes": os.path.getsize(filepath),
            "video": None,
            "audio": None,
            "duration": None,
            "duration_hms": "",
            "format_name": "未知",
            "format_long": "未知",
            "overall_bitrate": None,         # 总码率 bps
            "overall_bitrate_str": "",        # "5000 kbps"
            "container": "未知",
            "error": None,
            "_raw_streams": raw.get("streams", []),
        }

        fmt = raw.get("format", {})
        info["duration"] = self._safe_float(fmt.get("duration"))
        dur = info["duration"]
        if dur:
            h = int(dur // 3600)
            m = int((dur % 3600) // 60)
            s = int(dur % 60)
            info["duration_hms"] = f"{h:02d}:{m:02d}:{s:02d}"

        info["format_name"] = self._resolve_format_name(filepath, fmt.get("format_name", "未知"))
        info["format_long"] = fmt.get("format_long_name", "未知")
        info["container"] = info["format_name"]

        raw_br = self._safe_int(fmt.get("bit_rate"))
        info["overall_bitrate"] = raw_br
        info["overall_bitrate_str"] = self._fmt_bitrate(raw_br)

        streams = raw.get("streams", [])
        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "video" and info["video"] is None:
                info["video"] = self._parse_video(stream, info.get("duration"))
            elif codec_type == "audio" and info["audio"] is None:
                info["audio"] = self._parse_audio(stream)

        return info

    # ─────────────────────── 视频流 ───────────────────────
    def _parse_video(self, stream, duration):
        # ---- 帧率：优先 avg_frame_rate（VFR 视频更准确）----
        fps = self._parse_fps(stream)

        # ---- 分辨率 & SAR 修正 ----
        w = stream.get("width")
        h = stream.get("height")

        # 显示分辨率（考虑 SAR 非 1:1 的情况）
        dar_w, dar_h = w, h
        sar_str = stream.get("sample_aspect_ratio", "1:1")
        sar_w, sar_h = 1, 1
        if sar_str and ":" in sar_str:
            parts = sar_str.split(":")
            try:
                sar_w = float(parts[0])
                sar_h = float(parts[1])
            except ValueError:
                pass
        if sar_w and sar_h and sar_h != 0:
            dar_w = int(w * sar_w / sar_h) if w else None

        # 旋转元数据
        rotation = self._get_rotation(stream)
        if rotation in (90, 270):
            dar_w, dar_h = h, w

        # ---- 码率 ----
        raw_vb = self._safe_int(stream.get("bit_rate"))
        if raw_vb is None and duration and duration > 0:
            # 尝试从 tags 中获取
            tags = stream.get("tags", {})
            raw_vb = self._safe_int(tags.get("BPS") or tags.get("variant_bitrate"))

        # ---- 像素格式 / 色彩 ----
        pix_fmt = stream.get("pix_fmt", "未知")
        color_space = stream.get("color_space", "未知")
        color_transfer = stream.get("color_transfer", "未知")
        color_primaries = stream.get("color_primaries", "未知")
        color_range = stream.get("color_range", "未知")
        bits_per_raw = stream.get("bits_per_raw_sample")

        # HDR 检测
        is_hdr = (
            color_transfer in ("smpte2084", "arib-std-b67", "smpte2084", "hlg") or
            color_primaries in ("bt2020", "smpte432")
        )

        return {
            "codec": stream.get("codec_name", "未知"),
            "codec_long": stream.get("codec_long_name", "未知"),
            "codec_tag": stream.get("codec_tag_string", ""),
            "profile": stream.get("profile", "未知"),
            "level": self._safe_float(stream.get("level")),
            "width": w,
            "height": h,
            "display_width": dar_w,
            "display_height": dar_h,
            "resolution": f"{w}x{h}" if w else "未知",
            "aspect_ratio": self._aspect_ratio_str(w, h, sar_w, sar_h),
            "display_aspect_ratio": self._aspect_ratio_str(dar_w, dar_h, 1, 1),
            "fps": fps,
            "fps_exact": self._parse_exact_fps(stream),
            "pix_fmt": pix_fmt,
            "bits_per_sample": bits_per_raw,
            "color_space": color_space,
            "color_transfer": color_transfer,
            "color_primaries": color_primaries,
            "color_range": color_range,
            "is_hdr": is_hdr,
            "bitrate": raw_vb,
            "bitrate_str": self._fmt_bitrate(raw_vb),
            "rotation": rotation,
        }

    # ─────────────────────── 音频流 ───────────────────────
    def _parse_audio(self, stream):
        sr = self._safe_int(stream.get("sample_rate"))
        channels = stream.get("channels")
        layout = stream.get("channel_layout", "未知")
        raw_ab = self._safe_int(stream.get("bit_rate"))
        fmt = stream.get("sample_fmt", "未知")

        # 位深度映射
        bps = self._parse_audio_bps(fmt)

        # 语言
        tags = stream.get("tags", {})
        lang = tags.get("language", "")

        return {
            "codec": stream.get("codec_name", "未知"),
            "codec_long": stream.get("codec_long_name", "未知"),
            "codec_tag": stream.get("codec_tag_string", ""),
            "sample_rate": sr,
            "sample_rate_str": f"{sr / 1000:.1f} kHz" if sr else "未知",
            "channels": channels,
            "channels_str": self._channels_str(channels, layout),
            "channel_layout": layout,
            "bitrate": raw_ab,
            "bitrate_str": self._fmt_bitrate(raw_ab),
            "sample_fmt": fmt,
            "bits_per_sample": bps,
            "language": lang,
        }

    # ─────────────────────── 辅助 ───────────────────────

    @staticmethod
    def _resolve_format_name(filepath: str, raw_format_name: str) -> str:
        """将 FFprobe 返回的逗号分隔多格式列表解析为单一具体格式。

        FFprobe 的 format_name 字段是 demuxer 支持的所有格式列表，
        如 "mov,mp4,m4a,3gp,3g2" — 需要根据文件扩展名匹配出实际格式。
        """
        # FFprobe 常见 demuxer 列表 → 用户可读格式名映射
        FORMAT_DISPLAY_MAP = {
            "mov": "MOV", "mp4": "MP4", "m4a": "M4A", "3gp": "3GP",
            "3g2": "3G2", "mkv": "MKV", "matroska": "MKV", "webm": "WebM",
            "avi": "AVI", "flv": "FLV", "wmv": "WMV", "asf": "ASF",
            "mpeg": "MPEG", "mpegts": "TS", "ts": "TS", "m2ts": "M2TS",
            "mts": "MTS", "vob": "VOB", "ogv": "OGV", "rm": "RMVB",
            "rmvb": "RMVB", "divx": "DIVX", "dv": "DV", "mxf": "MXF",
            "mpj2": "MPJ2", "mpeg1video": "MPEG-1",
            "mpeg2video": "MPEG-2", "mpegvideo": "MPEG",
            "rawvideo": "RAW", "h264": "H.264", "hevc": "H.265",
        }

        # 如果没有逗号，直接映射
        if "," not in raw_format_name:
            return FORMAT_DISPLAY_MAP.get(raw_format_name.lower(), raw_format_name.upper())

        # 有逗号：按文件扩展名从列表中匹配
        ext = os.path.splitext(filepath)[1].lower().lstrip(".")  # "mp4"
        candidates = [f.strip() for f in raw_format_name.split(",")]

        # 优先匹配扩展名
        for c in candidates:
            if c.lower() == ext:
                return FORMAT_DISPLAY_MAP.get(c.lower(), c.upper())

        # 扩展名不在列表中，用映射表尝试常见扩展名映射
        EXT_TO_FORMAT = {
            ".mp4": "mp4", ".mov": "mov", ".m4v": "mp4", ".m4a": "m4a",
            ".3gp": "3gp", ".3g2": "3g2", ".mkv": "matroska", ".webm": "webm",
            ".avi": "avi", ".flv": "flv", ".wmv": "asf", ".asf": "asf",
            ".mpg": "mpeg", ".mpeg": "mpeg", ".ts": "mpegts",
            ".m2ts": "mpegts", ".mts": "mpegts", ".vob": "mpeg",
            ".ogv": "ogv", ".rmvb": "rmvb", ".rm": "rm",
            ".divx": "avi", ".dv": "dv", ".mxf": "mxf",
        }
        mapped = EXT_TO_FORMAT.get(f".{ext}")
        if mapped:
            return FORMAT_DISPLAY_MAP.get(mapped.lower(), mapped.upper())

        # 兜底：返回列表第一个的映射名
        first = candidates[0]
        return FORMAT_DISPLAY_MAP.get(first.lower(), first.upper())

    @staticmethod
    def _fmt_bitrate(bps):
        """格式化码率：自动选择 kbps 或 Mbps"""
        if bps is None:
            return "未知"
        if bps >= 1_000_000:
            return f"{bps / 1_000_000:.2f} Mbps"
        return f"{bps // 1000} kbps"

    @staticmethod
    def _aspect_ratio_str(w, h, sar_w, sar_h):
        """计算比例字符串，如 "16:9" """
        if not w or not h:
            return "未知"
        pw = w * sar_w
        ph = h * sar_h
        from math import gcd
        g = gcd(int(pw), int(ph))
        return f"{int(pw)//g}:{int(ph)//g}"

    @staticmethod
    def _parse_fps(stream):
        """帧率解析：优先 avg_frame_rate，降级 r_frame_rate"""
        for key in ("avg_frame_rate", "r_frame_rate"):
            val = stream.get(key, "")
            if val and "/" in val:
                parts = val.split("/")
                try:
                    if parts[1] != "0":
                        return round(float(parts[0]) / float(parts[1]), 2)
                except (ValueError, ZeroDivisionError):
                    pass
        return None

    @staticmethod
    def _parse_exact_fps(stream):
        """原始帧率字符串（精确表达式）"""
        for key in ("avg_frame_rate", "r_frame_rate"):
            val = stream.get(key, "")
            if val and "/" in val:
                return val  # "30000/1001"
        return None

    @staticmethod
    def _get_rotation(stream):
        """获取旋转角度"""
        side_data_list = stream.get("side_data_list", [])
        for sd in side_data_list:
            rot = sd.get("rotation")
            if rot is not None:
                return rot
        tags = stream.get("tags", {})
        rot_tag = tags.get("rotate")
        if rot_tag:
            try:
                return int(rot_tag)
            except (ValueError, TypeError):
                pass
        return 0

    @staticmethod
    def _parse_audio_bps(sample_fmt):
        """音频样本格式 → 位深度"""
        fmt_map = {
            "s16": 16, "s16p": 16,
            "s32": 32, "s32p": 32, "flt": 32, "fltp": 32,
            "s24": 24, "s24p": 24,
            "dbl": 64, "dblp": 64,
            "u8": 8, "u8p": 8,
        }
        return fmt_map.get(sample_fmt)

    @staticmethod
    def _channels_str(channels, layout):
        """易读声道数"""
        layout_map = {"mono": 1, "stereo": 2, "2.1": 3, "3.0": 3,
                      "4.0": 4, "5.0": 5, "5.1": 6, "7.1": 8}
        if channels is None:
            return "未知"
        for name, count in layout_map.items():
            if name in (layout or "").lower():
                return f"{channels}ch ({name})"
        return f"{channels}ch"

    @staticmethod
    def _safe_float(val):
        try:
            return round(float(val), 2) if val else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(val):
        try:
            return int(float(val)) if val else None
        except (TypeError, ValueError):
            return None
