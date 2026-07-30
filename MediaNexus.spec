# -*- mode: python ; coding: utf-8 -*-
"""
MediaNexus - PyInstaller 打包配置（onedir 模式）
运行：python -m PyInstaller MediaNexus.spec --clean --noconfirm
产出：dist/MediaNexus/ 目录（含 MediaNexus.exe + 全部 DLL / assets / docs）
       配合 installer/MediaNexus-Setup.iss 一键打包为 Windows 安装程序
"""
import os
import sys
from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

# 兜底 1：collect_dynamic_libs 钩子（标准做法，部分 Python 发行版有效）
_sqlite3_binaries = collect_dynamic_libs('sqlite3')

# 兜底 2：显式从源 Python 的多个标准位置搜索 sqlite3.dll 与 Visual C++
# 运行时一起加进 bundle。适用场景：
#   - 标准官方 Python：sqlite3.dll 在 DLLs/ 子目录
#   - Miniconda：sqlite3.dll 在 Library/bin/ 子目录（Conda 特有约定，
#     PyInstaller 默认钩子不识别此布局，会漏检，导致运行时
#     "DLL load failed while importing _sqlite3: 找不到指定的模块"）
#   - VC 运行时（vcruntime140/msvcp140）通常在 Python 根目录或 DLLs
_extra_binaries = []
_py_root = os.path.dirname(sys.executable)
_search_dirs = (
    os.path.join(_py_root, 'DLLs'),          # 标准官方 Python / Conda 的 .pyd
    _py_root,                                  # Python 根目录（vcruntime 等常在此）
    os.path.join(_py_root, 'Library', 'bin'),  # Conda 特有：sqlite3.dll 等
    os.path.join(_py_root, 'Library', 'lib'),  # Conda 备选位置
)
for _dll_name in (
    'sqlite3.dll',                  # SQLite 原生库（_sqlite3.pyd 依赖，Conda 关键漏检项）
    'libbz2.dll', 'LIBBZ2.dll',      # bzip2（_bz2.pyd 依赖）
    'libmpdec-4.dll',                 # decimal（_decimal.pyd 依赖）
    'libexpat.dll',                  # XML 解析（pyexpat.pyd 依赖）
    'ffi.dll',                       # ctypes（_ctypes.pyd 依赖）
    'vcruntime140.dll',              # MSVC 运行时
    'vcruntime140_1.dll',            # MSVC 运行时（Py3.12+ 新增）
    'msvcp140.dll',                  # MSVC C++ 标准库
    'msvcp140_1.dll',                # MSVC C++ 标准库 v1
    'concrt140.dll',                 # MSVC 并发库
    'vccorlib140.dll',               # MSVC 协程库
):
    for _d in _search_dirs:
        _p = os.path.join(_d, _dll_name)
        if os.path.isfile(_p):
            _extra_binaries.append((_p, '.'))
            break  # 已找到，不要重复

a = Analysis(
    ['MediaNexus/main.py'],
    pathex=['.'],
    binaries=_sqlite3_binaries + _extra_binaries,
    datas=[
        ('assets', 'assets'),
        ('docs', 'docs'),
        # 内置 FFmpeg（完整版静态构建）：gyan.dev 的 full 构建，包含 ffmpeg.exe +
        # ffprobe.exe + ffplay.exe 及全部编解码器/滤镜，覆盖现有及后续扩展的全部需求。
        # 打包前请先运行：python scripts/fetch_ffmpeg.py（一键拉取完整版到此处）。
        ('resources/ffmpeg', 'resources/ffmpeg'),
    ],
    hiddenimports=[
        'aiofiles', 'aiofiles.os',
        'rapidfuzz', 'rapidfuzz.fuzz', 'rapidfuzz.utils',
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebChannel',
        'openpyxl', 'cv2', 'numpy',
        # FFmpeg 管理器（QC 引擎依赖，确保被收集）
        'utils.ffmpeg_manager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'tkinter', 'unittest', 'test', 'pip'],
    noarchive=False,
)

pyz = PYZ(a.pure)

# onedir 模式：exe 与所有 DLL 放在同一目录（dist/MediaNexus/）。
# 这彻底避开了「单文件 + 临时目录解包」带来的 native DLL 路径问题（如
# _sqlite3 报「找不到指定的模块」），也是 Inno Setup 安装器最自然的输入。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MediaNexus',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 不显示黑色控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',  # 应用图标（透明版 Logo 生成的多分辨率 ICO）
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MediaNexus',
)
