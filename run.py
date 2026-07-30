# -*- coding: utf-8 -*-
"""项目启动器：将包路径加入 sys.path 后启动应用。

同时做一层友好的依赖缺失保护：若未安装 PySide6 等依赖，
不再让控制台一闪而过，而是弹出可读的错误提示。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 全局崩溃捕获：务必在创建 QApplication / 导入其余模块之前安装，
# 这样即使后续初始化阶段抛异常，也能落日志 + 弹窗，避免打包后"闪退无迹"。
try:
    from MediaNexus.crash_handler import install as _install_crash_handler

    _install_crash_handler()
except Exception:  # 绝不让捕获器自身导致启动失败
    pass


def _show_error(title, msg):
    """尽量用图形弹窗报错；PySide6 不可用时退化为打印到 stderr。"""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        owns_app = app is None
        if owns_app:
            app = QApplication(sys.argv)
        QMessageBox.critical(None, title, msg)
        if owns_app:
            app.quit()
    except Exception:
        print(f"[ERROR] {title}\n{msg}", file=sys.stderr)


def _main():
    try:
        from MediaNexus.main import main
    except ImportError as exc:
        _show_error(
            "缺少运行依赖",
            "未能导入必要的依赖库（通常是 PySide6 / rapidfuzz / aiofiles 未安装）。\n\n"
            "请在本项目目录下执行：\n"
            "    pip install -r requirements.txt\n\n"
            "然后重新运行：\n"
            "    python run.py\n\n"
            f"原始错误：{exc}",
        )
        return 1
    # 确保相对路径资源（assets/arrows/ 等）始终可解析
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    return main() or 0


if __name__ == "__main__":
    sys.exit(_main())
