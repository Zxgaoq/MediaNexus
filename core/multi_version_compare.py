"""
多版本视频对比模块

功能：
- 接收多个文件夹路径，每个文件夹代表一个"版本"（如不同音频/水印）。
- 假设各文件夹内文件名相同（同一视频编号的不同版本）。
- 对同一编号的所有版本，横向比对其时长、帧率、编码、帧数是否完全一致。
- 调用现有 video_probe.VideoProbe 读取元数据，只读取不解码，保持高时效性。
- 输出一致性结果，支持导出 Excel。
"""
import os
import re
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from core.video_probe import VideoProbe

logger = logging.getLogger("MediaNexus.QC.MultiVersionCompare")

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
    ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts",
    ".m2ts", ".mts", ".vob", ".ogv", ".rmvb", ".divx",
}


def natural_sort_key(s: str) -> list:
    """自然排序键：把字符串切成文本/数字片段，数字按 int 比较。

    效果：['1.mp4', '2.mp4', '10.mp4', '11.mp4', 'a.mp4']
    """
    parts = re.split(r"(\d+)", s or "")
    return [int(p) if p.isdigit() else p.lower() for p in parts]


@dataclass
class VersionFile:
    """单个版本文件的信息"""
    version_name: str          # 文件夹名（版本名）
    folder_path: str
    filepath: str
    filename: str
    file_id: str = ""          # 文件名去扩展名，作为分组 key
    duration: Optional[float] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    frame_count: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format_name: Optional[str] = None
    bitrate: Optional[int] = None
    error: Optional[str] = None


@dataclass
class GroupResult:
    """同一文件编号的对比结果"""
    file_id: str                 # 文件名（去扩展名）
    versions: List[VersionFile] = field(default_factory=list)
    duration_consistent: bool = True
    fps_consistent: bool = True
    codec_consistent: bool = True
    frame_count_consistent: bool = True
    resolution_consistent: bool = True
    format_consistent: bool = True
    all_consistent: bool = True
    messages: List[str] = field(default_factory=list)


@dataclass
class CompareResult:
    """整个对比任务的结果"""
    groups: List[GroupResult] = field(default_factory=list)
    version_names: List[str] = field(default_factory=list)
    total_files: int = 0
    consistent_groups: int = 0
    inconsistent_groups: int = 0


class MultiVersionComparator:
    """多版本视频对比器

    只使用 FFprobe 读取元数据，不逐帧解码，保证大批量文件时的时效性。
    """

    def __init__(self, progress_callback=None):
        self.probe = VideoProbe()
        self.progress_callback = progress_callback

    def compare(self, folder_paths: List[str]) -> CompareResult:
        """
        执行多版本对比。

        Args:
            folder_paths: 版本文件夹路径列表，顺序作为版本列顺序。

        Returns:
            CompareResult
        """
        result = CompareResult()
        if not folder_paths:
            return result

        # 收集每个文件夹里的视频文件
        version_files_map: Dict[str, List[VersionFile]] = {}
        for folder_path in folder_paths:
            version_name = os.path.basename(folder_path) or folder_path
            result.version_names.append(version_name)
            files = self._scan_video_files(folder_path)
            version_files_map[version_name] = files

        # 按 file_id 分组
        groups_by_id: Dict[str, GroupResult] = defaultdict(lambda: GroupResult(file_id=""))
        for version_name, files in version_files_map.items():
            for vf in files:
                file_id = vf.file_id
                groups_by_id[file_id].file_id = file_id
                groups_by_id[file_id].versions.append(vf)

        # 读取每个文件元数据
        all_files = [vf for files in version_files_map.values() for vf in files]
        result.total_files = len(all_files)
        for idx, vf in enumerate(all_files):
            self._probe_file(vf)
            if self.progress_callback:
                self.progress_callback(int((idx + 1) / len(all_files) * 100), vf.filename)

        # 逐个组判定一致性
        for file_id in sorted(groups_by_id.keys(), key=natural_sort_key):
            group = groups_by_id[file_id]
            self._analyze_group(group)
            result.groups.append(group)
            if group.all_consistent:
                result.consistent_groups += 1
            else:
                result.inconsistent_groups += 1

        return result

    def _scan_video_files(self, folder_path: str) -> List[VersionFile]:
        """扫描文件夹内所有视频文件"""
        files = []
        if not os.path.isdir(folder_path):
            return files
        for entry in os.scandir(folder_path):
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    filename = entry.name
                    file_id = os.path.splitext(filename)[0]
                    version_name = os.path.basename(folder_path) or folder_path
                    files.append(VersionFile(
                        version_name=version_name,
                        folder_path=folder_path,
                        filepath=entry.path,
                        filename=filename,
                        file_id=file_id,
                    ))
        return sorted(files, key=lambda x: x.filename)

    def _probe_file(self, vf: VersionFile):
        """使用现有 VideoProbe 读取元数据"""
        try:
            info = self.probe.probe(vf.filepath)
            vf.duration = info.get("duration")
            video = info.get("video") or {}
            vf.fps = video.get("fps")
            vf.codec = video.get("codec")
            vf.width = video.get("width")
            vf.height = video.get("height")
            vf.bitrate = video.get("bitrate")
            vf.format_name = info.get("format_name") or info.get("container") or "未知"

            # 帧数：优先使用 FFprobe 的 nb_frames，不存在时用 duration*fps
            vf.frame_count = self._estimate_frame_count(info, vf.duration, vf.fps)
        except Exception as e:
            logger.error(f"探测失败: {vf.filepath} -> {e}")
            vf.error = str(e)

    @staticmethod
    def _estimate_frame_count(info: dict, duration: Optional[float], fps: Optional[float]) -> Optional[int]:
        """估算帧数：优先取 FFprobe 流级 nb_frames，否则 duration*fps"""
        info.get("video") or {}
        # 流级 nb_frames
        raw_streams = info.get("_raw_streams", info.get("streams", []))
        if isinstance(raw_streams, list):
            for s in raw_streams:
                if s.get("codec_type") == "video":
                    nb = s.get("nb_frames")
                    if nb and str(nb).isdigit():
                        return int(nb)
        # 备选
        if duration and fps:
            return int(round(duration * fps))
        return None

    def _analyze_group(self, group: GroupResult):
        """分析同一 file_id 下多版本是否一致"""
        versions = group.versions
        if len(versions) <= 1:
            return

        # 过滤掉探测失败的
        valid = [v for v in versions if not v.error]
        if len(valid) < 2:
            group.all_consistent = False
            group.messages.append("有效版本数量不足，无法对比")
            return

        # 基准取第一个有效版本
        base = valid[0]
        checks = [
            ("duration", "时长", lambda v: v.duration, 0.05),
            ("fps", "帧率", lambda v: v.fps, 0.0),
            ("codec", "视频编码", lambda v: v.codec, None),
            ("frame_count", "帧数", lambda v: v.frame_count, 0.0),
            ("resolution", "分辨率", lambda v: (v.width, v.height), None),
            ("format", "格式", lambda v: v.format_name, None),
        ]

        for attr, label, getter, tolerance in checks:
            base_val = getter(base)
            consistent = True
            if base_val is None:
                consistent = False
                group.messages.append(f"{label} 基准值缺失")
            else:
                for v in valid[1:]:
                    val = getter(v)
                    if val is None:
                        consistent = False
                        group.messages.append(f"{label} 在版本 [{v.version_name}] 缺失")
                    elif tolerance is not None and isinstance(base_val, (int, float)) and isinstance(val, (int, float)):
                        if abs(base_val - val) > tolerance:
                            consistent = False
                            group.messages.append(f"{label} 不一致：基准 {base_val} vs [{v.version_name}] {val}")
                    elif base_val != val:
                        consistent = False
                        group.messages.append(f"{label} 不一致：基准 {base_val} vs [{v.version_name}] {val}")

            setattr(group, f"{attr}_consistent", consistent)
            if not consistent:
                group.all_consistent = False

        if group.all_consistent:
            group.messages.append("所有版本完全一致")
