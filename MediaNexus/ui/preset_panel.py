# -*- coding: utf-8 -*-
"""
检测预设参数编辑面板
独立的 QC 预设参数面板，不直接依赖 QC ConfigManager，
改为读写 MediaNexus config_manager 的 qc_presets / qc_active_preset。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# 参数定义：(config_key, 显示名, min, max, step, default, tooltip)
_PARAM_GROUPS = [
    ("黑帧检测", [
        ("black_frame.mean_pixel_threshold", "像素阈值 (0-255)", 0, 255, 1, 3,
         "低于此平均像素值的画面判定为黑帧"),
        ("black_frame.min_duration", "最少持续帧数", 1, 30, 1, 1,
         "连续黑帧数少于此时忽略"),
    ]),
    ("黑边检测（悬崖探测 + 众数稳定性）", [
        ("black_border.cliff_gradient_min", "悬崖梯度阈值", 5, 50, 1, 25,
         "亮度剖面梯度≥此值视为人工黑边边界（自然暗边缘梯度5-15，人工黑边30+）"),
        ("black_border.border_mean_max", "黑边区域亮度上限", 5, 30, 1, 6,
         "候选黑边区域均值≤此值才认定（真实黑边0-15，自然暗区15-40）"),
        ("black_border.border_std_max", "黑边区域方差上限", 3, 20, 1, 6,
         "候选黑边区域Std≤此值才认定（人工黑条Std≈0-5，暗区Std≈10-30）"),
        ("black_border.contrast_ratio_min", "对比度比下限", 1.0, 10.0, 0.1, 4.0,
         "内容亮度/黑边亮度≥此值才认定（暗场景也能检测，替代旧的绝对阈值）"),
        ("black_border.min_border_px", "最小黑边宽度 (px)", 3, 50, 1, 3,
         "低于此像素宽度的黑边不报告（≈1%画面高度，肉眼可见阈值）"),
        ("black_border.mode_ratio_min", "众数稳定性阈值", 0.70, 1.00, 0.01, 0.90,
         "段内有值帧中≥此比例宽度一致才确认（真黑边=1.0，暗场景<0.90=过滤）"),
    ]),
    ("静音检测", [
        ("silence.rms_threshold", "RMS 能量阈值 (0-1)", 0.0, 0.1, 0.001, 0.005,
         "音频 RMS 能量低于此阈值判定为静音"),
        ("silence.min_duration_ignore", "忽略阈值 (秒)", 0.1, 5.0, 0.1, 0.5,
         "短于此秒数的静音忽略"),
        ("silence.min_duration_warn", "警告阈值 (秒)", 0.5, 10.0, 0.1, 2.0,
         "超过此秒数标记为警告"),
        ("silence.min_duration_error", "错误阈值 (秒)", 1.0, 30.0, 0.5, 5.0,
         "超过此秒数标记为错误"),
    ]),
]


class PresetParamPanel(QWidget):
    """检测预设参数编辑面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spinboxes: dict[str, QWidget] = {}
        self._init_ui()

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setObjectName("settingsInnerScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setLineWidth(0)

        container = QWidget()
        container.setObjectName("settingsInnerContent")
        main_layout = QVBoxLayout(container)

        for group_title, params in _PARAM_GROUPS:
            main_layout.addWidget(self._create_group(group_title, params))

        scroll.setWidget(container)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _create_group(self, title: str, params: list) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout()

        for key, label, min_val, max_val, step, default, tooltip in params:
            if isinstance(step, float):
                spin = QDoubleSpinBox()
                spin.setDecimals(3)
            else:
                spin = QSpinBox()

            spin.setRange(min_val, max_val)
            spin.setSingleStep(step)
            spin.setValue(default)
            spin.setToolTip(tooltip)
            spin.setMinimumWidth(120)

            self._spinboxes[key] = spin
            form.addRow(QLabel(label), spin)

        group.setLayout(form)
        return group

    def load_thresholds(self, thresholds: dict) -> None:
        """将阈值 dict 加载到各 spinbox。"""
        for key, spin in self._spinboxes.items():
            keys = key.split(".")
            value = thresholds
            try:
                for k in keys:
                    value = value[k]
                spin.blockSignals(True)
                if isinstance(spin, QSpinBox):
                    spin.setValue(int(value))
                else:
                    spin.setValue(float(value))
                spin.blockSignals(False)
            except (KeyError, TypeError, ValueError):
                pass

    def get_thresholds(self) -> dict:
        """从各 spinbox 收集阈值 dict。"""
        thresholds: dict = {}
        for key, spin in self._spinboxes.items():
            keys = key.split(".")
            current = thresholds
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = spin.value()
        return thresholds
