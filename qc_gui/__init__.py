"""
gui/widgets — 影枢 QC 的 UI 小组件包

将原本集中在 main_window.py 的界面构建拆分为独立的 Widget 类，
每个 Widget 只负责自身 UI 构建并暴露内部控件，交互逻辑（信号处理）
仍由 MainWindow 统一编排，从而保证重构前后行为一致。
"""

from qc_gui.widgets.file_panel import FilePanel
from qc_gui.widgets.result_panel import ResultPanel
from qc_gui.widgets.detail_panel import DetailPanel
from qc_gui.widgets.toolbar import Toolbar
from qc_gui.widgets.bottom_bar import BottomBar
from qc_gui.widgets.status_bar import StatusBar

__all__ = [
    "FilePanel",
    "ResultPanel",
    "DetailPanel",
    "Toolbar",
    "BottomBar",
    "StatusBar",
]
