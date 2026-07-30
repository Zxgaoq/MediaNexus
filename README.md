# MediaSync — 素材同步与视频质检桌面工具

> **MediaSync = ProjectSync（素材同步）+ VideoQC（视频质检）**
>
> 一个面向影视素材生产流程的 Windows 桌面应用：
> - 让本地项目目录与服务器素材目录建立项目级关联
> - 以三栏界面浏览本地 / 服务器内容并执行复制、移动等操作
> - 对视频执行黑帧、夹帧、黑边、静音、一致性、多版本对比等 QC 检测
> - 导出 Excel 检测报告

---

## 目录

1. [项目概览](#1-项目概览)
2. [环境要求](#2-环境要求)
3. [开发启动](#3-开发启动)
4. [核心能力](#4-核心能力)
5. [架构与目录](#5-架构与目录)
6. [配置与数据](#6-配置与数据)
7. [构建与发布](#7-构建与发布)
8. [测试与验证](#8-测试与验证)
9. [常见问题](#9-常见问题)
10. [开发文档](#10-开发文档)

---

## 1. 项目概览

| 项目 | 说明 |
| --- | --- |
| 产品名 | **MediaSync** |
| 运行形态 | Windows 桌面应用，基于 **PySide6** |
| 系统形态 | 单进程、模块化桌面单体 |
| 主入口 | `run.py`（开发入口） |
| 打包入口 | `ProjectSync_Studio/main.py` |
| 主配置 | `%APPDATA%/MediaSync/config.json` |
| 索引数据库 | `%APPDATA%/MediaSync/nas_index.db` |
| QC 缓存 | `%APPDATA%/MediaSync/qc_cache.db` |
| 分发形态 | PyInstaller **onedir** + Inno Setup 安装器 |

> 当前源码已经统一使用 `%APPDATA%/MediaSync/` 作为运行时配置目录。旧目录 `%APPDATA%/ProjectSyncStudio/` 仅用于兼容迁移，不应再作为新文档或新功能的默认路径。

---

## 2. 环境要求

- **操作系统**：Windows 10 / 11
- **Python**：3.10+
- **GUI 依赖**：PySide6
- **视频检测依赖**：OpenCV、NumPy、openpyxl
- **网络环境**：可访问目标服务器 / NAS 共享目录
- **FFmpeg**：可使用系统 PATH、手动指定目录、随包内置目录或 `%APPDATA%/MediaSync/ffmpeg/bin`

依赖列表见：`requirements.txt`

---

## 3. 开发启动

```bash
# 安装依赖
python -m pip install -r requirements.txt

# 启动主程序
python run.py

# 或直接走包入口
python -m ProjectSync_Studio.main

# 环境自检
python diagnose.py
```

### 启动链路

```text
run.py
  -> 安装 crash_handler
  -> import ProjectSync_Studio.main.main
  -> 切换工作目录到项目根
  -> 调用 ProjectSync_Studio.main.main()

ProjectSync_Studio.main.main()
  -> 再次安装 crash_handler
  -> 调用 ProjectSync_Studio.ui.main_window.run_app()
  -> 创建 QApplication 并显示主窗口
```

---

## 4. 核心能力

### 4.1 ProjectSync：素材同步

- 管理本地项目与服务器项目的关联关系
- 扫描服务器素材根目录并建立本地 SQLite 索引
- 对项目名做归一化与模糊匹配
- 通过三栏界面显示：
  - 左栏：项目导航
  - 中栏：本地项目目录
  - 右栏：服务器项目目录
- 支持复制、移动、重命名、新建、删除、拖拽上传/下载等文件操作

### 4.2 VideoQC：视频质检

- 黑帧检测
- 夹帧 / 闪帧检测
- 黑边检测
- 静音检测
- 多文件一致性检查
- 多版本文件夹对比
- Excel 报告导出

### 4.3 关键实现特点

- **服务器索引缓存**：避免频繁直接遍历 NAS
- **QThread 后台任务**：避免界面线程阻塞
- **单次视频解码复用**：`FrameScanner` 一次解码同时服务多个视觉检测器
- **统一配置源**：主程序与 QC 共用同一份配置与预设

---

## 5. 架构与目录

```text
MediaSync-QC-Studio/
├── run.py                         # 开发启动器
├── ProjectSync_Studio/            # 主程序包
│   ├── main.py                    # PyInstaller 入口
│   ├── constants.py               # 常量、路径、样式、状态枚举
│   ├── config_manager.py          # 主配置单例
│   ├── crash_handler.py           # 崩溃捕获与日志
│   ├── indexer.py                 # 服务器索引器 NASIndexer
│   ├── matcher.py                 # 项目匹配逻辑
│   ├── workers.py                 # 后台线程任务
│   ├── qc_bridge.py               # 打开 QC 窗口 / 多版本对比
│   └── ui/                        # 主窗口与各面板
├── core/                          # 无 GUI 依赖的 QC 领域核心
├── qc_gui/                        # QC 独立窗口与控件
├── utils/                         # FFmpeg、配置代理、导出、存储等基础设施
├── docs/                          # 用户文档
├── dev/                           # 开发文档
├── installer/                     # Inno Setup 脚本
├── ProjectSync_Studio.spec        # PyInstaller onedir 配置
├── config.json                    # 示例 / fallback 配置
└── tests/                         # 冒烟测试
```

### 模块边界

| 模块 | 职责 |
| --- | --- |
| `ProjectSync_Studio` | 主程序、项目管理、服务器索引、文件浏览、设置、启动链路 |
| `core` | 视频 QC 核心算法与检测编排 |
| `qc_gui` | QC 窗口、结果展示、交互控件 |
| `utils` | FFmpeg 管理、配置代理、Excel 导出、缓存与文档查看 |

### 边界规则

- `core/` 不应依赖 PySide6
- UI 层不应直接承载耗时 I/O，必须交给 Worker
- 主配置唯一权威来源是 `ProjectSync_Studio/config_manager.py`
- 新增视觉检测优先复用 `FrameScanner`，不要重复全量解码视频

---

## 6. 配置与数据

### 6.1 主配置

运行时主配置：`%APPDATA%/MediaSync/config.json`

其中主要包含：

- `local_roots`
- `nas_roots`
- `projects`
- `settings`
- `qc_presets`
- `qc_active_preset`
- `qc_settings`
- `indexed_at`

### 6.2 项目模型要点

当前项目模型以**服务器项目路径**为主要锚点。

配置中的：

- `local_name`：历史字段名，当前更接近**内部唯一键**
- `name`：展示名称
- `local_path`：本地目录
- `confirmed_nas_path`：已确认的服务器目录

> `local_name` 不应再被理解为“本地项目名称”。在服务器优先的工作流里，它通常等于服务器项目路径。

### 6.3 索引与缓存

- `nas_index.db`：服务器目录索引，使用 SQLite WAL
- `qc_cache.db`：QC 结果缓存，按 `path + size + mtime` 命中

### 6.4 FFmpeg 路径优先级

1. 系统 PATH
2. 用户手动指定目录
3. 随包内置 `resources/ffmpeg`
4. `%APPDATA%/MediaSync/ffmpeg/bin`

---

## 7. 构建与发布

### 7.1 PyInstaller

```bash
python -m PyInstaller ProjectSync_Studio.spec --clean --noconfirm
```

输出目录：

```text
dist/MediaSync/
```

这是 **onedir** 分发，不是单文件 exe。

### 7.2 Inno Setup

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\MediaSync-Setup.iss
```

安装器输出：

```text
dist/installer/MediaSync-Setup.exe
```

### 7.3 发布说明

- 安装包不会删除 `%APPDATA%/MediaSync` 下的用户配置和缓存
- 打包的目标是发布验证，不是日常开发主流程

---

## 8. 测试与验证

### 冒烟测试

```bash
python -m pytest tests/ -q
```

当前 `tests/test_smoke.py` 主要覆盖：

- 版本号契约
- 默认忽略词
- 索引器重建与子项读取
- 并发写稳定性
- 只读连接隔离
- matcher 归一化与评分
- FFmpegManager 接口与手动目录解析

### 建议验证项

| 修改范围 | 最低验证 |
| --- | --- |
| 配置 / 索引 / 匹配 | 运行 `pytest tests/ -q` |
| UI 文件操作 | 手动运行 `python run.py` |
| QC 检测器 | 用样本视频验证黑帧 / 夹帧 / 黑边 / 静音 |
| 打包逻辑 | 启动 `dist/MediaSync/MediaSync.exe` |
| 安装器 | 构建并验证安装 / 升级 / 卸载 |

---

## 9. 常见问题

### Q1：为什么 README 和旧认知不一致？

因为项目已经发生演进，当前应以源码、`ProjectSync_Studio.spec` 和 `dev/DevHandbook.*` 为准。旧描述里常见的过时信息包括：

- 旧配置目录 `%APPDATA%/ProjectSyncStudio`
- 单文件 exe 分发
- 误把 `local_name` 当作展示名称

### Q2：QC 结果为什么没有更新？

先检查 `qc_cache.db` 是否命中。同一路径、文件大小、修改时间一致时会复用缓存；可在设置中清理 QC 缓存后重测。

### Q3：为什么不能在子线程里直接创建缩略图图标？

因为 `QPixmap` 必须在主线程创建。当前实现要求子线程只生成 `QImage`，主线程再转换为 `QPixmap/QIcon`。

### Q4：为什么打包后还要看包入口？

因为 PyInstaller 直接使用 `ProjectSync_Studio/main.py` 作为入口，不能只在 `run.py` 里做全局初始化或异常保护。

---

## 10. 开发文档

- HTML 版开发手册：`dev/DevHandbook.html`
- Markdown 版开发手册：`dev/DevHandbook.md`

如果你是维护者，建议优先阅读开发手册，而不是只依赖 README。
