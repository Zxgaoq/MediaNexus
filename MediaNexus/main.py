# -*- coding: utf-8 -*-
"""
MediaNexus - 包入口
支持两种运行方式：
  * 开发：python run.py   （见项目根目录 run.py）
  * 打包：PyInstaller 以本文件为入口脚本
"""
from MediaNexus.ui.main_window import run_app


def main():
    # 全局崩溃捕获：务必在创建 QApplication / 进入事件循环之前安装，
    # 这样未捕获异常与 Qt 致命错误都能落日志（%APPDATA%/MediaNexus/crash.log）+ 弹窗，
    # 避免打包后"闪退无迹"。PySide6 已在上方 import run_app 时被加载，故此处可一并装好 Qt 消息钩子。
    try:
        from MediaNexus.crash_handler import install as _install_crash

        _install_crash()
    except Exception:  # 绝不让捕获器自身导致启动失败
        pass

    run_app()


if __name__ == "__main__":
    main()
