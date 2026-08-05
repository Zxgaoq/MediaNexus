"""
配置管理模块
读取/写入用户配置文件 config.json
所有用户设置、预设参数保存在可执行文件同级的 config.json 中
"""

import os
import json
import logging
from copy import deepcopy

logger = logging.getLogger("MediaNexus.QC.Config")


# ---------------------------------------------------------------------------
# 主程序（MediaNexus / MediaNexus）配置单例的懒加载
# ---------------------------------------------------------------------------
# 当本模块在 MediaNexus 主程序进程内被拉起时，QC 的配置应直接复用主程序的
# %APPDATA% 配置文件（qc_presets / qc_active_preset / qc_settings），由主程序统一
# 落盘，从而彻底消除「根目录 config.json」与「%APPDATA% 配置」双源漂移。
# 独立运行 QC（未加载主程序）时回退到本地 config.json。
_HOST_CM_CACHE = None
_HOST_CM_RESOLVED = False


def _resolve_host_config_manager():
    """懒加载主程序配置单例；不可用时返回 None（仅解析一次）。"""
    global _HOST_CM_CACHE, _HOST_CM_RESOLVED
    if _HOST_CM_RESOLVED:
        return _HOST_CM_CACHE
    _HOST_CM_RESOLVED = True
    try:
        from MediaNexus.config_manager import config_manager as cm
        _HOST_CM_CACHE = cm
    except Exception:
        _HOST_CM_CACHE = None
    return _HOST_CM_CACHE


# 默认阈值配置（与预设 default 保持一致）
DEFAULT_THRESHOLDS = {
    "black_frame": {
        "mean_pixel_threshold": 3,
        "min_duration": 1,
    },
    "black_border": {
        "cliff_gradient_min": 25,
        "border_mean_max": 6,
        "border_std_max": 6,
        "contrast_ratio_min": 4.0,
        "min_border_px": 3,
        "mode_ratio_min": 0.90,
    },
    "silence": {
        "rms_threshold": 0.005,
        "min_duration_ignore": 0.5,
        "min_duration_warn": 2.0,
        "min_duration_error": 5.0,
    },
    "performance": {
        "max_threads": 4,
        "max_duration_for_full_scan": 600,
    },
}

# 默认预设标准 — 单一默认预设
DEFAULT_PRESETS = {
    "default": {
        "name": "默认预设",
        "description": "影枢 QC 默认检测参数，适用于大多数视频质检场景",
        "thresholds": {
            "black_frame": {"mean_pixel_threshold": 3, "min_duration": 1},
            "black_border": {"cliff_gradient_min": 25, "border_mean_max": 6, "border_std_max": 6, "contrast_ratio_min": 4.0, "min_border_px": 3, "mode_ratio_min": 0.90},
            "silence": {"rms_threshold": 0.005, "min_duration_ignore": 0.5, "min_duration_warn": 2.0, "min_duration_error": 5.0},
        }
    }
}

# 参数说明与推荐值
PARAMETER_GUIDE = {
    "black_frame.mean_pixel_threshold": {
        "name": "黑帧像素阈值",
        "explanation": "当画面平均像素值低于此阈值时，判定为黑帧。值越小越严格。",
        "range": "0-50",
        "recommended": "8-15",
        "risk_low": "调低此值可能导致漏判：暗场过渡场景可能不会被标记为黑帧。",
        "risk_high": "调高此值可能导致误判：正常暗光画面可能被错误标记为黑帧。",
    },
    "black_border.cliff_gradient_min": {
        "name": "悬崖梯度阈值",
        "explanation": "亮度剖面中梯度≥此值视为悬崖式突变（人工黑边特征）。自然暗边缘梯度通常5-15，人工黑边30-200+。",
        "range": "5-50",
        "recommended": "10-20",
        "risk_low": "调低可能导致暗边缘误判为黑边：阴影渐变可能通过更低阈值。",
        "risk_high": "调高可能导致低对比度黑边漏判：轻微编码噪点的黑边可能梯度不够。",
    },
    "black_border.border_mean_max": {
        "name": "黑边区域亮度上限",
        "explanation": "候选黑边区域均值≤此值才认定。真实黑边均值0-15，自然暗区15-40。",
        "range": "5-30",
        "recommended": "10-20",
        "risk_low": "调高可能导致自然暗区误判为黑边。",
        "risk_high": "调低可能导致编码噪点黑边漏判（噪点均值可能达到8-15）。",
    },
    "black_border.border_std_max": {
        "name": "黑边区域方差上限",
        "explanation": "候选黑边区域标准差≤此值才认定。人工黑条Std≈0-5（均匀），自然暗区Std≈10-30（有纹理）。",
        "range": "3-20",
        "recommended": "6-12",
        "risk_low": "调高可能导致有纹理的暗区误判为黑边。",
        "risk_high": "调低可能导致高噪点黑边漏判（压缩噪点Std可能达到5-8）。",
    },
    "black_border.contrast_ratio_min": {
        "name": "黑边对比度比下限",
        "explanation": "内容亮度/黑边亮度的最低比值。替代旧的绝对亮度阈值，暗场景也能检测。真实黑边对比度≥3，暗边缘1.5-2.5。",
        "range": "1.0-10.0",
        "recommended": "2.0-4.0",
        "risk_low": "调低可能导致暗边缘误判为黑边。",
        "risk_high": "调高可能导致暗场景中的真实黑边漏判。",
    },
    "black_border.min_border_px": {
        "name": "最小黑边宽度",
        "explanation": "黑边宽度低于此像素数不报告。设为3可检测7px等极细黑边；设为4时可能被跨帧一致性过滤丢弃。",
        "range": "3-50",
        "recommended": "3-8",
        "risk_low": "调低可能导致微小边缘误报（编码伪影、阴影）。",
        "risk_high": "调高可能导致真实但较窄的黑边漏判。",
    },
    "black_border.mode_ratio_min": {
        "name": "众数稳定性阈值",
        "explanation": "段内有值帧中≥此比例宽度一致才确认（真黑边宽度从不改变）。默认0.90=90%一致，低于此值=暗场景/阴影。",
        "range": "0.70-1.00",
        "recommended": "0.85-0.95",
        "risk_low": "调低可能将暗场景误报为黑边（宽度不稳定）。",
        "risk_high": "调高可能将窄黑边（偶尔检测失败）误过滤。",
    },
    "silence.rms_threshold": {
        "name": "静音 RMS 能量阈值",
        "explanation": "音频 RMS 能量值低于此阈值时判定为静音。",
        "range": "0-0.1",
        "recommended": "0.005-0.02",
        "risk_low": "调低此值可能导致漏判：极低音量的段落可能被忽略。",
        "risk_high": "调高此值可能导致误判：低声旁白或环境音可能被标记为静音。",
    },
    "silence.min_duration_error": {
        "name": "静音错误级别时长",
        "explanation": "连续静音超过此秒数标记为错误级别。",
        "range": "0.5-30",
        "recommended": "3-8",
        "risk_low": "可能忽略本应引起注意的长时间静音。",
        "risk_high": "过短的静音片段也可能触发红色警告，增加检查负担。",
    },
}


class ConfigManager:
    """配置管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config_path = self._get_config_path()
        self._config = {}
        self._dirty = False
        self._load()

    def _get_config_path(self):
        """获取配置文件路径。

        若运行在 MediaNexus（MediaNexus）主程序进程内，复用主程序的
        %APPDATA% 配置文件（与 qc_presets / qc_active_preset 同源），避免
        出现「根目录 config.json」与「%APPDATA% 配置」双源漂移。
        """
        host = self._host_cm()
        if host is not None:
            return host._path
        from utils.storage_manager import StorageManager
        return StorageManager().config_path

    def _host_cm(self):
        """返回主程序配置单例；非主程序内环境返回 None。"""
        return _resolve_host_config_manager()

    def _load(self):
        """加载配置。

        优先从主程序（MediaNexus）的 %APPDATA% 配置读取 qc_presets /
        qc_active_preset / qc_settings；否则回退到本地 config.json（独立运行 QC 时）。
        仅对新创建的预设补全字段，不修改已有预设的用户参数。
        """
        host = self._host_cm()
        raw_presets = None
        raw_active = None
        raw_settings = {}
        source_desc = ""

        if host is not None:
            raw_presets = host.qc_presets
            raw_active = host.qc_active_preset
            raw_settings = (host.data or {}).get("qc_settings", {}) or {}
            source_desc = f"主程序配置 {host._path}"
        elif os.path.isfile(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    file_cfg = json.load(f)
                # 兼容旧版顶层 presets / 新版 qc_presets
                raw_presets = file_cfg.get("qc_presets", file_cfg.get("presets", {}))
                raw_active = file_cfg.get(
                    "qc_active_preset", file_cfg.get("active_preset", "default")
                )
                raw_settings = file_cfg.get("qc_settings", {})
                source_desc = f"本地配置 {self._config_path}"
            except Exception as e:
                logger.error(f"配置文件加载失败: {e}，使用默认配置")
                raw_presets = None

        # 构造内部配置（以默认值打底，再覆盖）
        self._config = self._get_defaults()
        presets = deepcopy(raw_presets) if raw_presets else deepcopy(DEFAULT_PRESETS)
        active = raw_active or "default"
        if active not in presets:
            active = "default"

        # 迁移：删除旧版内置预设（broadcast/streaming/mobile），保留用户自定义预设
        legacy_keys = {"broadcast", "streaming", "mobile"}
        legacy_found = [k for k in presets if k in legacy_keys]
        if legacy_found:
            for k in legacy_found:
                del presets[k]
            logger.info(f"已迁移删除旧版内置预设: {legacy_found}")
            self._dirty = True

        # 确保 default 预设存在
        if "default" not in presets:
            presets["default"] = deepcopy(DEFAULT_PRESETS["default"])
            self._dirty = True

        # 仅补全缺失的阈值字段，不覆盖已有值
        for preset_key, preset_data in presets.items():
            preset_t = preset_data.setdefault("thresholds", {})
            for section, values in DEFAULT_PRESETS["default"]["thresholds"].items():
                if section not in preset_t:
                    preset_t[section] = deepcopy(values)
                    self._dirty = True
                    logger.info(f"补全预设 '{preset_key}' 缺失的阈值组: {section}")
                else:
                    for k, v in values.items():
                        if k not in preset_t[section]:
                            preset_t[section][k] = v
                            self._dirty = True
                            logger.info(f"补全预设 '{preset_key}' 缺失的阈值项: {section}.{k}")

        # 迁移：旧版 black_border 参数 → 新版悬崖探测参数
        old_bb_keys = {"edge_pixel_threshold", "valid_ratio_min", "edge_scan_width"}
        new_bb_defaults = DEFAULT_PRESETS["default"]["thresholds"]["black_border"]
        for preset_key, preset_data in presets.items():
            bb_section = preset_data.get("thresholds", {}).get("black_border", {})
            if any(k in bb_section for k in old_bb_keys):
                for k in old_bb_keys:
                    bb_section.pop(k, None)
                for k, v in new_bb_defaults.items():
                    bb_section.setdefault(k, v)
                self._dirty = True
                logger.info(f"迁移预设 '{preset_key}' 旧版黑边参数 → 新版悬崖探测参数")

        self._config["presets"] = presets
        self._config["active_preset"] = active
        self._config["thresholds"] = presets.get(active, {}).get(
            "thresholds", deepcopy(DEFAULT_THRESHOLDS)
        )
        # 应用 qc_settings（独立运行时的主题/语言/输出目录等）
        self._config["theme"] = raw_settings.get("theme", "light")
        self._config["language"] = raw_settings.get("language", "zh_CN")
        self._config["last_output_dir"] = raw_settings.get("last_output_dir", "")
        self._config["window_geometry"] = raw_settings.get("window_geometry", "")
        self._config["performance"] = raw_settings.get(
            "performance", deepcopy(DEFAULT_THRESHOLDS["performance"])
        )

        if source_desc:
            logger.info(f"已加载 QC 配置: {source_desc}")
        if self._dirty:
            self.save()

    def _get_defaults(self):
        """获取默认配置"""
        return {
            "thresholds": deepcopy(DEFAULT_THRESHOLDS),
            "presets": deepcopy(DEFAULT_PRESETS),
            "active_preset": "default",
            "last_output_dir": "",
            "window_geometry": "",
            "language": "zh_CN",
            "theme": "light",
            "performance": deepcopy(DEFAULT_THRESHOLDS["performance"]),
        }

    def save(self, force=False):
        """保存配置。

        若运行在 MediaNexus 主程序内，直接写入主程序配置单例的 qc_presets /
        qc_active_preset / qc_settings，由主程序统一落盘，避免覆盖其 projects/settings。
        否则写回本地 config.json（qc_* 命名空间）。
        """
        if not self._dirty and not force:
            return
        host = self._host_cm()
        qc_settings = {
            "theme": self._config.get("theme", "light"),
            "language": self._config.get("language", "zh_CN"),
            "last_output_dir": self._config.get("last_output_dir", ""),
            "window_geometry": self._config.get("window_geometry", ""),
            "performance": self._config.get(
                "performance", DEFAULT_THRESHOLDS["performance"]
            ),
        }
        if host is not None:
            host.qc_presets = self._config.get("presets", {})
            host.qc_active_preset = self._config.get("active_preset", "default")
            host.data.setdefault("qc_settings", {})
            host.data["qc_settings"] = qc_settings
            host.save()
            self._dirty = False
            logger.info(f"QC 配置已写入主程序配置: {host._path}")
            return
        # 独立运行：写本地 config.json
        try:
            existing = {}
            if os.path.isfile(self._config_path):
                try:
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}
            existing["qc_presets"] = self._config.get("presets", {})
            existing["qc_active_preset"] = self._config.get("active_preset", "default")
            existing["qc_settings"] = qc_settings
            # 清理旧版顶层键，避免与 qc_* 命名空间混淆
            for legacy in ("presets", "active_preset", "thresholds"):
                existing.pop(legacy, None)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            self._dirty = False
            logger.info(f"配置已保存: {self._config_path}")
        except Exception as e:
            logger.error(f"配置保存失败: {e}")

    def get(self, key, default=None):
        """获取配置项，支持点号分隔的嵌套键"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key, value, persist=True):
        """设置配置项，支持点号分隔的嵌套键。
        persist=False 时只改内存不写磁盘（用于会话级临时设置）。
        """
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        if persist:
            self._dirty = True
            self.save()

    @property
    def thresholds(self):
        """获取当前活跃的阈值配置（返回深拷贝，防止意外修改）"""
        active_preset = self.get("active_preset", "default")
        presets = self.get("presets", {})
        if active_preset in presets:
            return deepcopy(presets[active_preset].get("thresholds", DEFAULT_THRESHOLDS))
        return deepcopy(self.get("thresholds", DEFAULT_THRESHOLDS))

    @property
    def performance(self):
        """获取性能配置"""
        return self.get("performance", DEFAULT_THRESHOLDS["performance"])

    def get_threshold(self, key, default=None):
        """获取当前活跃预设下的阈值"""
        thresholds = self.thresholds
        keys = key.split(".")
        value = thresholds
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def presets(self):
        """获取所有预设"""
        return self.get("presets", {})

    @property
    def active_preset(self):
        """获取当前活跃预设名称"""
        return self.get("active_preset", "default")

    @property
    def theme(self):
        """获取当前主题: 'light' 或 'dark'"""
        return self.get("theme", "light")

    @theme.setter
    def theme(self, value):
        """设置当前主题"""
        self.set("theme", value)
