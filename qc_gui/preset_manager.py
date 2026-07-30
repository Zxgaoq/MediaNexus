"""
预设管理器
管理内置预设和用户自定义预设。
"""

import json
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout,
    QDoubleSpinBox, QSpinBox, QMessageBox, QWidget, QTabWidget,
    QTextEdit, QScrollArea,
)
from PySide6.QtCore import Qt, Signal

from utils.config import ConfigManager, PARAMETER_GUIDE, DEFAULT_PRESETS
from qc_gui.styles import COLORS

logger = logging.getLogger("VideoQC.PresetManager")


class PresetDialog(QDialog):
    """预设管理对话框"""

    preset_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.setWindowTitle("预设管理")
        self.setMinimumSize(900, 650)
        self.setModal(True)
        self._init_ui()
        self._load_presets()

    def _init_ui(self):
        layout = QHBoxLayout(self)

        # 左侧：预设列表
        left_panel = QVBoxLayout()

        title = QLabel("可用预设")
        title.setProperty("cssClass", "header")
        left_panel.addWidget(title)

        self.preset_list = QListWidget()
        self.preset_list.currentRowChanged.connect(self._on_preset_selected)
        left_panel.addWidget(self.preset_list)

        btn_layout = QHBoxLayout()
        self.btn_activate = QPushButton("启用预设")
        self.btn_activate.setProperty("cssClass", "primary")
        self.btn_activate.clicked.connect(self._activate_preset)
        btn_layout.addWidget(self.btn_activate)

        self.btn_delete = QPushButton("删除")
        self.btn_delete.setProperty("cssClass", "danger")
        self.btn_delete.clicked.connect(self._delete_preset)
        btn_layout.addWidget(self.btn_delete)

        left_panel.addLayout(btn_layout)

        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setMaximumWidth(300)
        layout.addWidget(left_widget)

        # 右侧：参数编辑区
        right_panel = QVBoxLayout()

        self.edit_tabs = QTabWidget()

        # 参数面板
        self.param_panel = PresetParamPanel(self.config)
        self.edit_tabs.addTab(self.param_panel, "检测参数")

        # 说明面板
        self.guide_panel = QTextEdit()
        self.guide_panel.setReadOnly(True)
        self.edit_tabs.addTab(self.guide_panel, "参数说明")

        right_panel.addWidget(self.edit_tabs)

        # 按钮区
        btn_box = QHBoxLayout()

        self.btn_save = QPushButton("保存修改")
        self.btn_save.setProperty("cssClass", "primary")
        self.btn_save.clicked.connect(self._save_preset)
        btn_box.addWidget(self.btn_save)

        self.btn_new = QPushButton("新建预设")
        self.btn_new.clicked.connect(self._new_preset)
        btn_box.addWidget(self.btn_new)

        self.btn_export = QPushButton("导出预设")
        self.btn_export.clicked.connect(self._export_preset)
        btn_box.addWidget(self.btn_export)

        self.btn_import = QPushButton("导入预设")
        self.btn_import.clicked.connect(self._import_preset)
        btn_box.addWidget(self.btn_import)

        btn_box.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)

        right_panel.addLayout(btn_box)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        layout.addWidget(right_widget)

    def _load_presets(self):
        """加载预设列表"""
        self.preset_list.clear()
        presets = self.config.presets
        active = self.config.active_preset

        for key, preset in presets.items():
            text = f"{preset['name']}"
            if key == active:
                text += " [当前]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setData(Qt.ItemDataRole.UserRole + 1, json.dumps(preset))
            self.preset_list.addItem(item)

        if self.preset_list.count() > 0:
            self.preset_list.setCurrentRow(0)

    def _on_preset_selected(self, row):
        if row < 0:
            return
        item = self.preset_list.item(row)
        key = item.data(Qt.ItemDataRole.UserRole)
        preset_data = json.loads(item.data(Qt.ItemDataRole.UserRole + 1))

        thresholds = preset_data.get("thresholds", {})
        self.param_panel.load_thresholds(thresholds)

        # 更新说明
        desc = preset_data.get("description", "无描述")
        guide_text = f"# {preset_data['name']}\n\n{desc}\n\n---\n\n"
        guide_text += self._generate_parameter_guide()
        self.guide_panel.setMarkdown(guide_text)

        self._current_key = key

    def _generate_parameter_guide(self):
        """生成参数说明"""
        lines = ["## 参数说明\n"]
        for key, guide in PARAMETER_GUIDE.items():
            lines.append(f"### {guide['name']}")
            lines.append(f"- **说明**: {guide['explanation']}")
            lines.append(f"- 🔽 调低风险: {guide['risk_low']}")
            lines.append(f"- 🔼 调高风险: {guide['risk_high']}")
            lines.append("")
        return "\n".join(lines)

    def _activate_preset(self):
        """激活选中的预设"""
        if not self._current_key:
            return

        self.config.set("active_preset", self._current_key)
        QMessageBox.information(self, "提示", f"已启用预设: {self.config.presets[self._current_key]['name']}")
        self.preset_changed.emit(self._current_key)
        self._load_presets()

    def _save_preset(self):
        """保存当前预设修改"""
        if not hasattr(self, '_current_key') or not self._current_key:
            QMessageBox.warning(self, "提示", "请先选择一个预设")
            return

        thresholds = self.param_panel.get_thresholds()
        preset_key = self._current_key

        # 直接修改内存中的预设配置并强制写盘
        presets = self.config._config.get("presets", {})
        if preset_key in presets:
            presets[preset_key]["thresholds"] = thresholds
            # 强制保存（绕过 _dirty 标记）
            self.config.save(force=True)
            QMessageBox.information(self, "提示", f"预设 '{presets[preset_key]['name']}' 已保存")
            # 刷新列表显示
            self._load_presets()
            # 通知主窗口预设已变更
            self.preset_changed.emit(preset_key)
        else:
            QMessageBox.warning(self, "提示", f"预设 '{preset_key}' 不存在")

    def _new_preset(self):
        """新建自定义预设"""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建预设", "请输入预设名称:")
        if not ok or not name.strip():
            return

        key = name.strip().lower().replace(" ", "_")
        presets = self.config.get("presets", {})

        if key in presets:
            QMessageBox.warning(self, "提示", f"预设 '{key}' 已存在")
            return

        presets[key] = {
            "name": name.strip(),
            "description": "自定义预设",
            "thresholds": self.param_panel.get_thresholds(),
        }
        self.config.set("presets", presets)
        self._load_presets()
        QMessageBox.information(self, "提示", f"预设 '{name}' 已创建")

    def _delete_preset(self):
        """删除自定义预设"""
        if not hasattr(self, '_current_key') or not self._current_key:
            return

        # 内置预设不可删除
        if self._current_key in DEFAULT_PRESETS:
            QMessageBox.warning(self, "提示", "内置预设不可删除")
            return

        reply = QMessageBox.question(self, "确认删除",
                                      f"确定要删除预设 '{self._current_key}' 吗？",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        presets = self.config.get("presets", {})
        if self._current_key in presets:
            del presets[self._current_key]
            self.config.set("presets", presets)

            # 如果删除的是当前活跃预设，切换到默认
            if self.config.active_preset == self._current_key:
                self.config.set("active_preset", "streaming")

            self._load_presets()
            self.preset_changed.emit("streaming")

    def _export_preset(self):
        """导出预设为 JSON 文件"""
        from PySide6.QtWidgets import QFileDialog
        if not hasattr(self, '_current_key') or not self._current_key:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "导出预设", f"{self._current_key}.json", "JSON Files (*.json)"
        )
        if not path:
            return

        presets = self.config.get("presets", {})
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(presets[self._current_key], f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "提示", f"预设已导出到: {path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def _import_preset(self):
        """从 JSON 文件导入预设"""
        from PySide6.QtWidgets import QFileDialog, QInputDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "导入预设", "", "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                preset_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入失败: {e}")
            return

        name, ok = QInputDialog.getText(self, "导入预设", "请输入预设名称:",
                                         text=preset_data.get("name", ""))
        if not ok or not name.strip():
            return

        key = name.strip().lower().replace(" ", "_")
        preset_data["name"] = name.strip()
        if "description" not in preset_data:
            preset_data["description"] = "导入的预设"
        if "thresholds" not in preset_data:
            preset_data["thresholds"] = {}

        presets = self.config.get("presets", {})
        presets[key] = preset_data
        self.config.set("presets", presets)
        self._load_presets()
        QMessageBox.information(self, "提示", f"预设 '{name}' 已导入")


class PresetParamPanel(QWidget):
    """预设参数编辑面板"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._spinboxes = {}
        self._init_ui()

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        main_layout = QVBoxLayout(container)

        # 黑帧检测参数
        main_layout.addWidget(self._create_group(
            "黑帧检测",
            [
                ("black_frame.mean_pixel_threshold", "像素阈值 (0-255)", 0, 255, 1, 3,
                 "低于此平均像素值的画面判定为黑帧"),
                ("black_frame.min_duration", "最少持续帧数", 1, 30, 1, 1,
                 "连续黑帧数少于此时忽略"),
            ]
        ))

        # 黑边检测参数（v3 悬崖探测 + 众数稳定性）
        main_layout.addWidget(self._create_group(
            "黑边检测（悬崖探测 + 众数稳定性）",
            [
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
            ]
        ))

        # 静音检测参数
        main_layout.addWidget(self._create_group(
            "静音检测",
            [
                ("silence.rms_threshold", "RMS 能量阈值 (0-1)", 0.0, 0.1, 0.001, 0.005,
                 "音频 RMS 能量低于此阈值判定为静音"),
                ("silence.min_duration_ignore", "忽略阈值 (秒)", 0.1, 5.0, 0.1, 0.5,
                 "短于此秒数的静音忽略"),
                ("silence.min_duration_warn", "警告阈值 (秒)", 0.5, 10.0, 0.1, 2.0,
                 "超过此秒数标记为警告"),
                ("silence.min_duration_error", "错误阈值 (秒)", 1.0, 30.0, 0.5, 5.0,
                 "超过此秒数标记为错误"),
            ]
        ))

        scroll.setWidget(container)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _create_group(self, title, params):
        """创建一个参数组"""
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

            # 添加警告标签
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(spin)

            # 风险提示标签
            hint_label = QLabel("")
            hint_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
            hint_label.setWordWrap(True)
            self._spinboxes[f"{key}_hint"] = hint_label
            row_layout.addWidget(hint_label)

            # 连接值变化信号
            spin.valueChanged.connect(lambda v, k=key: self._on_value_changed(k, v))

            form.addRow(QLabel(label), row_widget)

        group.setLayout(form)
        return group

    def _on_value_changed(self, key, value):
        """参数值变化时的实时提示"""
        from utils.config import PARAMETER_GUIDE
        guide = PARAMETER_GUIDE.get(key)

        hint_key = f"{key}_hint"
        if hint_key not in self._spinboxes:
            return

        hint_label = self._spinboxes[hint_key]
        if not guide:
            hint_label.setText("")
            return

        # 判断是偏低还是偏高
        rec = guide.get("recommended", "")
        try:
            if "-" in rec:
                low, high = map(float, rec.split("-"))
                if value < low:
                    hint_label.setText(f"⚠ {guide['risk_low']}")
                    hint_label.setStyleSheet(f"color: {COLORS['warning_text']}; font-size: 11px;")
                elif value > high:
                    hint_label.setText(f"⚠ {guide['risk_high']}")
                    hint_label.setStyleSheet(f"color: {COLORS['error_text']}; font-size: 11px;")
                else:
                    hint_label.setText(f"✓ 在推荐范围内 ({rec})")
                    hint_label.setStyleSheet(f"color: {COLORS['pass_text']}; font-size: 11px;")
        except:
            pass

    def load_thresholds(self, thresholds):
        """加载阈值到控件"""
        for key, spin in self._spinboxes.items():
            if key.endswith("_hint"):
                continue
            keys = key.split(".")
            value = thresholds
            try:
                for k in keys:
                    value = value[k]
                spin.blockSignals(True)
                # QSpinBox 接受 int，QDoubleSpinBox 接受 float
                if isinstance(spin, QSpinBox):
                    spin.setValue(int(value))
                else:
                    spin.setValue(float(value))
                spin.blockSignals(False)
            except (KeyError, TypeError, ValueError):
                pass

    def get_thresholds(self):
        """获取当前控件中的阈值"""
        thresholds = {}
        for key, spin in self._spinboxes.items():
            if key.endswith("_hint"):
                continue
            keys = key.split(".")
            current = thresholds
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = spin.value()
        return thresholds
