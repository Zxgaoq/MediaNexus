# -*- coding: utf-8 -*-
"""环境诊断脚本：运行前检查 Python 版本、依赖、包路径、配置。"""
import os
import sys


def main():
    print("=" * 60)
    print("MediaSync 环境诊断")
    print("=" * 60)
    print(f"Python 版本：{sys.version}")
    print(f"当前工作目录：{os.getcwd()}")
    print(f"运行命令：{' '.join(sys.argv)}")
    print(f"python 解释器：{sys.executable}")
    print()

    # 检查关键依赖（含 VideoQC 子系统所需）
    missing = []
    for pkg in ["PySide6", "rapidfuzz", "aiofiles", "cv2", "numpy", "openpyxl"]:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "unknown")
            print(f"  {pkg}: {ver}")
        except ImportError as e:
            print(f"  {pkg}: 未安装或导入失败 -> {e}")
            missing.append(pkg)
    print()

    # 检查项目包是否能导入
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        import ProjectSync_Studio
        print(f"ProjectSync_Studio 包：可导入")
        print(f"  包路径：{ProjectSync_Studio.__file__}")
    except Exception as e:  # noqa: BLE001
        print(f"ProjectSync_Studio 包：导入失败 -> {type(e).__name__}: {e}")
        return

    try:
        from ProjectSync_Studio.config_manager import config_manager
        from ProjectSync_Studio.constants import CONFIG_PATH, INDEX_DB_PATH

        print(f"  配置文件路径：{CONFIG_PATH}")
        print(f"  索引数据库路径：{INDEX_DB_PATH}")
        print(f"  本地根目录：{config_manager.local_roots or '（未设置）'}")
        print(f"  NAS 根目录：{config_manager.nas_roots or '（未设置）'}")
    except Exception as e:  # noqa: BLE001
        print(f"  配置读取失败 -> {type(e).__name__}: {e}")
    print()

    if missing:
        print("结论：缺少依赖，请运行：")
        print("  pip install -r requirements.txt")
    else:
        print("结论：依赖都已安装，可尝试启动：")
        print("  python run.py")
        print("如果仍无法运行，请把上面的完整输出 + 终端报错一起截图或复制给我。")


if __name__ == "__main__":
    main()
