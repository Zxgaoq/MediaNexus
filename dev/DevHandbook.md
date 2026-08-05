# MediaNexus 开发手册

> 版本：1.1.0
> 更新日期：2026-08-05
> 适用范围：当前仓库 `73d1ee017f0a5235c01c129711d18053aa964357` 及其工作区修改
> 维护对象：主程序、QC 窗口、构建脚本和测试

本文只描述当前代码真实存在的结构和行为。已经删除的模块、生成物和历史兼容逻辑分别标注，不能仅凭旧文档恢复目录或功能。

## 1. 审计结论

### 1.1 本轮检查范围

- 代码范围：`MediaNexus/`、`core/`、`qc_gui/`、`utils/`、`scripts/`、`tests/`、`run.py`。
- Python 文件：59 个；包含 5 个包初始化文件和 2 个测试文件。
- 入口：`run.py`、`MediaNexus.main`、`qc_gui.main_window`、`scripts.fetch_ffmpeg`，另加两个测试模块。
- 方法：Python AST 导入图、Ruff 未使用/未定义规则、动态导入与 Qt signal/slot 搜索、依赖检查、测试和编译检查。
- `fallow` 不适用于本项目：它只分析 TypeScript/JavaScript，本项目是 Python/PySide6，因此没有把它的结论冒充为 Python 死代码分析。

### 1.2 结论和处理

| 项目 | 结论 |
| --- | --- |
| 生产模块可达性 | 未发现孤立的生产模块；未直接出现在简化导入图中的 `__init__.py` 是正常包边界，不删除。 |
| 未使用导入/变量/未定义名称 | Ruff 规则 `F401/F841/F821/F811/F822/F823` 通过。 |
| 旧跨栏命令 | 已删除 `FileListView.send_to_peer` 和“发送到对侧”菜单；文件互传只走原生拖放语义。 |
| 旧缓存 API | 已删除无调用的 `StorageManager.get_cache_info()`、`clear_cache()` 和 `presets_backup_dir`；保留新缓存 API 和运行时迁移。 |
| 静态资源残留 | 已删除未被引用的 `assets/arrows/spin_up.svg`、`spin_down.svg`；箭头由运行时生成。 |
| 已删除历史文件 | `qc_gui/preset_manager.py`、`logo/`、旧调试脚本、`utils/logger.py`、空 `presets/` 等不属于当前源码。 |
| 兼容逻辑 | 配置 schema 迁移、旧 `logs/`/`exports/` 迁移、旧 `qc_cache.db` 清理和安装器旧注册表清理仍有运行时职责，不能按“无引用”删除。 |
| 未实现的 QC 占位 | 已删除没有检测器、阈值和实现文件的 `flash_frame` 结果字段、QC 展示分支和 Excel 导出分支。 |

### 1.3 验证基线

```text
python -m pytest tests/ -q                         -> 32 passed
python -m pip check                                -> No broken requirements found
python -m compileall -q MediaNexus core qc_gui utils scripts tests run.py
python -m ruff check ... --select F401,F841,F821,F811,F822,F823
```

构建目录、`dist/`、`build/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/` 和 `data/` 是生成或运行数据，不属于源码导入图。`data/logs/` 中的日志属于运行记录，不做自动删除。

## 2. 产品边界和不变量

MediaNexus 是 Windows 桌面单体应用，产品名为“影枢”，包含两个相互协作但边界清晰的部分：

1. 主工作台：项目管理、本地目录、服务器/NAS 目录、匹配、索引、复制/移动。
2. 影枢 QC：视频元数据、黑帧、黑边、静音、批量一致性和多版本对比。

当前业务逻辑不因 UI 重构改变，以下行为是接口契约：

- 双索引模式始终横向显示“左侧项目导航 | 中间本地内容 | 右侧服务器内容”，禁止改成上下布局。
- 服务器和本地内容必须在同一主窗口中同时可见；空的一侧显示状态，不通过隐藏另一侧制造布局跳变。
- 文件跨栏传送采用 Windows 原生拖放习惯：跨栏默认复制，同一列表拖入子文件夹默认移动；Ctrl 强制复制，Shift 强制移动。
- 不提供与拖放重复的“发送到对侧”命令。
- 所有网络目录扫描、文件复制/移动、视频检测都不能阻塞 GUI 线程。
- 主程序配置唯一权威来源是 `%APPDATA%\MediaNexus\config.json`；QC 在主程序内运行时复用这份配置。

## 3. 当前目录结构

```text
MediaNexus/
├── run.py                         开发启动器
├── README.md                      项目说明
├── requirements.txt               运行与打包依赖
├── config.json                    独立 QC 回退配置/默认模板
├── MediaNexus.spec                PyInstaller onedir 配置
├── build.bat                      PyInstaller 构建脚本
├── installer/
│   ├── MediaNexus-Setup.iss       Inno Setup 安装脚本
│   └── build-installer.bat        安装包构建脚本
├── MediaNexus/                    主程序包
│   ├── main.py                    PyInstaller 入口
│   ├── constants.py               路径、常量和主程序 QSS
│   ├── config_manager.py          主配置与 schema 迁移
│   ├── models.py                  Project 数据模型
│   ├── indexer.py                 SQLite NAS 索引
│   ├── matcher.py                 项目名称匹配
│   ├── workers.py                 索引、列表、复制和移动 Worker
│   ├── worker_manager.py          Worker 生命周期
│   ├── watcher.py                 NAS 实时监控
│   ├── qc_bridge.py               主程序到 QC 的窗口桥接
│   ├── clipboard.py               系统文件剪贴板
│   ├── crash_handler.py           崩溃日志与 Qt 消息捕获
│   ├── utils.py                   主程序文件/路径工具
│   └── ui/
│       ├── main_window.py         三栏工作台与全局调度
│       ├── left_sidebar.py        项目导航和项目菜单
│       ├── middle_panel.py        本地目录面板
│       ├── right_panel.py         服务器目录面板
│       ├── file_list_view.py      列表/缩略图/拖放/剪贴板
│       ├── add_project_dialog.py  添加项目
│       ├── select_match_dialog.py 手动选择匹配
│       ├── settings_dialog.py     设置
│       ├── preset_panel.py        QC 预设参数编辑
│       └── widgets.py             主程序小控件
├── core/                          无 GUI 的 QC 核心
│   ├── engine.py                  检测调度和批量一致性
│   ├── base_detector.py           检测器接口与注册表
│   ├── adapters.py                内置检测器适配器
│   ├── frame_scanner.py           单次视频解码
│   ├── black_frame.py             黑帧检测
│   ├── black_border.py            黑边检测
│   ├── silence_detect.py          静音检测
│   ├── video_probe.py             FFprobe 元数据
│   ├── consistency.py             多文件一致性
│   └── multi_version_compare.py   多版本对比
├── qc_gui/                        QC 独立窗口
│   ├── main_window.py             检测窗口和结果编排
│   ├── multi_version_compare_dialog.py
│   ├── styles.py                  QSS、图标生成和状态样式
│   ├── theme.py                   亮/暗主题
│   └── widgets/                   文件、结果、详情、工具栏、底栏、状态栏
├── utils/
│   ├── config.py                  QC 配置代理
│   ├── ffmpeg_manager.py          FFmpeg 定位、验证和下载
│   ├── exporter.py                Excel 导出
│   ├── storage_manager.py         运行数据和迁移
│   ├── docs_viewer.py             内嵌用户手册
│   └── onboarding.py              首次启动引导
├── assets/                        logo.png、logo.ico
├── resources/ffmpeg/              可选内置 ffmpeg/ffprobe
├── docs/MediaNexus-Manual.html    用户手册
├── dev/DevHandbook.md             本开发手册
├── scripts/fetch_ffmpeg.py        FFmpeg 下载工具
└── tests/                         冒烟与检测器测试
```

`build/`、`dist/`、`data/`、各类缓存目录可能在本地存在，但被 `.gitignore` 排除。它们不应被写进源码目录树，也不应作为 Python 模块提交。

## 4. 启动链路

### 4.1 开发启动

```text
python run.py
  -> 安装 crash_handler
  -> 导入 MediaNexus.main.main
  -> 切换当前目录到仓库根
  -> MediaNexus.ui.main_window.run_app()
  -> QApplication + 主程序 QSS + 首次启动引导
  -> MainWindow
```

`run.py` 只负责开发态路径、依赖错误提示和第一层崩溃保护；`MediaNexus/main.py` 是打包入口，因此包入口也必须安装崩溃捕获，不能只依赖 `run.py`。

### 4.2 其他入口

- `python -m MediaNexus.main`：包入口，行为与打包入口一致。
- `qc_gui.main_window`：QC 组件入口，正常情况下由 `MediaNexus.qc_bridge` 创建。
- `scripts.fetch_ffmpeg`：只下载/解压 FFmpeg，不启动 GUI。

## 5. 模块边界

| 边界 | 允许职责 | 禁止事项 |
| --- | --- | --- |
| `MediaNexus` | 主配置、项目、匹配、NAS 索引、Worker、主 UI | 把 QC 算法复制到主 UI |
| `MediaNexus/ui` | QWidget 构建、用户交互、信号编排 | 在 slot 中同步遍历 NAS 或解码视频 |
| `core` | 纯 Python/NumPy/OpenCV/FFmpeg QC 算法 | import PySide6、弹窗、直接修改 QWidget |
| `qc_gui` | QC 窗口、结果展示、主题、导出交互 | 维护第二份主程序配置 |
| `utils` | 配置代理、FFmpeg、存储、手册和 Excel | 反向依赖主 UI 组件 |

### 线程规则

- QWidget、QPixmap 和 UI 状态只在 GUI 线程操作；Worker 可生成 `QImage` 数据，但不创建/修改 QWidget。
- SQLite 写连接不能跨线程共享；查询使用 `NASIndexer._open_ro()` 创建调用线程独有的只读连接。
- 新增 QThread 必须登记到 `WorkerManager`，或明确归属 `NASWatcherManager`/面板局部生命周期。
- Worker 完成后清理 Python 引用；Qt C++ 对象被 `deleteLater()` 销毁后，旧 Python wrapper 不能继续调用 `isRunning()`。

## 6. 主工作台

### 6.1 三栏信息架构

`MediaNexus/ui/main_window.py` 创建一个横向 `QSplitter`：

```text
左：LeftSidebar       项目搜索、状态筛选、排序、项目菜单
中：MiddlePanel       本地项目目录、列表/缩略图、文件操作
右：RightPanel        服务器候选/确认目录、列表/缩略图、重试和实时刷新
```

默认尺寸为 `[260, 460, 460]`，三栏最小宽度为 140；双索引模式通过水平栏的可见性和内容状态处理，不创建第二套上下布局。仅本地/仅服务器模式只隐藏不参与的内容栏。

主窗口的顶部工具区提供扫描、重新匹配、设置、QC 检测和暂停；菜单提供文件、操作、帮助。状态栏禁用 `QSizeGrip`，进度只以永久控件显示，不能再叠加右下角任务按钮。

### 6.2 项目状态和加载顺序

```text
LeftSidebar.project_selected(key)
  -> MainWindow._on_project_selected(key)
  -> ConfigManager.get_project(key)
  -> MiddlePanel.load(local_path)
  -> RightPanel.load(project.confirmed_nas_path)
  -> 两侧 FileListView 分别加载当前目录
```

项目 key 仍使用历史字段 `local_name`，它是内部唯一键，不是显示名。显示名使用 `Project.display_name` 的规则：优先 `name`，否则使用路径末段。

项目状态：

- `matched`：已有确认服务器路径或有效匹配。
- `pending`：有候选但等待确认。
- `unmatched`：匹配完成但无可用候选。
- `none`：项目明确没有绑定服务器目录。

### 6.3 文件列表和拖放

`FileListView` 共享一个 `FileListViewModel`，用 `QTreeView` 提供列表模式，用 `QListView` 提供缩略图模式。目录优先、名称/大小/时间/类型排序，单次 `fetchMore()` 最多载入 `PAGE_SIZE=500` 行；搜索时对已加载目录数据做过滤。缩略图只处理支持的图片扩展名，并受 `THUMBNAIL_MAX_COUNT=400` 限制。

拖放契约：

| 场景 | 默认动作 | 实际 Worker |
| --- | --- | --- |
| 服务器文件拖到本地栏 | 复制 | `CopyWorker` |
| 本地文件拖到服务器栏 | 复制 | `CopyWorker` |
| 同一列表拖到子文件夹 | 移动 | `MoveWorker` |
| Ctrl 拖放 | 复制 | `CopyWorker` |
| Shift 拖放 | 移动 | `MoveWorker` |

拖放只传递 `QMimeData` 文件 URL；目标目录由落点目录项或当前目录决定。落地前统一调用 `check_overwrite_conflicts()`，同名冲突必须由用户确认。右键菜单和 `Ctrl+C/X/V` 仍可与 Windows 资源管理器文件剪贴板互操作，但不再提供跨栏发送命令。

### 6.4 添加项目

`AddProjectDialog` 从 SQLite 索引读取服务器根目录的直接子文件夹，并扫描本地根目录的直接子文件夹。每行包含勾选、服务器项目和本地匹配下拉框；本地独有目录也能单独添加。匹配候选走 `matcher.score_pair()`，阈值继承主配置。

## 7. 配置、索引和项目数据

### 7.1 配置来源

主程序配置：

```text
%APPDATA%\MediaNexus\config.json
%APPDATA%\MediaNexus\nas_index.db
```

`MediaNexus.config_manager.ConfigManager` 是主程序唯一写入入口，setter 默认即时保存，保存采用临时文件替换，避免半写文件。当前 schema 版本为 2，迁移链为 `v0 -> v1 -> v2`。

QC 配置代理 `utils.config.ConfigManager` 在主程序进程中优先读取主单例的 `qc_presets`、`qc_active_preset` 和 `qc_settings`；独立运行 QC 时回退到仓库根目录 `config.json`。不要在 `qc_gui` 中再创建第三份配置。

### 7.2 重要配置键

```text
local_roots / nas_roots
projects
settings.match_threshold
settings.ignore_patterns
settings.project_mode       both | local_only | server_only
settings.auto_refresh_enabled / auto_refresh_interval
settings.ffmpeg_manual_dir / ffmpeg_download_url
qc_presets / qc_active_preset / qc_settings
onboarding_done / indexed_at
```

任何 schema 变更都必须同时修改 `_default()`、增加迁移函数、递增 `CURRENT_SCHEMA_VERSION`，并补测试。不能只给新版本加默认键。

### 7.3 运行数据与缓存

`utils.storage_manager.StorageManager` 只管理当前实际存在的衍生文件，不把不存在的历史目录重新创建：

| 标识 | 位置 | 内容 | 设置页操作 |
| --- | --- | --- | --- |
| `audio_cache` | `data/cache/audio/` | 静音检测提取的临时 WAV | 统计、打开、清理 |
| `qc_cache` | `%APPDATA%\\MediaNexus\\qc_cache.db` | QC 检测结果缓存 | 统计、打开、清理 |
| `ffmpeg_cache` | `%APPDATA%\\MediaNexus\\ffmpeg\\` | 下载或解压的 FFmpeg | 统计、打开、清理 |
| `crash_log` | `%APPDATA%\\MediaNexus\\crash.log` | 崩溃与 Qt 消息日志 | 统计、打开、清理 |

`data/logs/` 和 `data/exports/` 仍由主程序/导出器使用，但不属于“缓存清理”按钮的目标；旧版根目录 `logs/`、`exports/` 的迁移由 `migrate_legacy_files()` 保留。新增缓存必须同时补充 `get_all_cache_info()`、`clear_all_caches()` 和测试，不能只在界面里添加一行文案。

### 7.4 NAS 索引

`NASIndexer` 维护 `entries(path, name, parent, is_dir, size, mtime)` 和 `meta` 表：

- `rebuild()`：全量重建；`fast=True` 先只建立项目级目录。
- `reindex_subtree()`：刷新单个子树。
- `refresh_dir()` / `refresh_dirs()`：watcher 事件驱动的单级 diff 写入。
- `query_all_folders()`：提供匹配候选。
- `list_children()`：提供右栏当前目录直接子项。

服务器列表优先从索引读取；索引不可用或用户手动刷新时，`ListWorker(force_live=True)` 回退到实时目录读取。全量写入和增量写入必须经过写锁，读取必须使用独立只读连接。

## 8. Worker 和实时监控

### 8.1 Worker 清单

| Worker | 用途 |
| --- | --- |
| `IndexWorker` | NAS 全量/快速索引 |
| `RefreshIndexWorker` | 无 watcher 时的服务器子树刷新 |
| `DeepScanWorker` | 添加项目后的后台深度索引 |
| `MatchWorker` | 本地项目与服务器候选匹配 |
| `ListWorker` | 目录子项读取 |
| `CopyWorker` | 文件/目录复制 |
| `MoveWorker` | 文件/目录移动 |
| `ThumbnailLoader` | QC/主列表中的图片缩略图加载 |
| `DetectionThread` | QC 批量检测 |
| `CompareThread` | QC 多版本对比 |

长生命周期主任务由 `WorkerManager` 注册；面板内的复制和缩略图线程由面板关闭逻辑停止；watcher 由 `NASWatcherManager` 管理。

### 8.2 NAS watcher

每个已确认的服务器项目根目录对应一个 `NASWatchThread`：

```text
QThread.run()
  -> 启动 daemon _blocking_reader()
  -> ReadDirectoryChangesW(递归)
  -> queue.Queue 回传事件
  -> QThread 每 0.3s 轮询
  -> 0.5s 防抖合并目录
  -> changed(root, affected_dirs)
  -> NASIndexer.refresh_dirs()
  -> 受影响的右栏同步读取索引并刷新
```

`ReadDirectoryChangesW` 在 NAS/SMB 上可能无限阻塞，不能直接放在 QThread 主体中，也不能把 `CloseHandle` 当作可靠中断。daemon 读取线程可随进程退出，QThread 仍需在约 0.3 秒内响应停止。

watcher 断连自动重连；事件缓冲区溢出或断连恢复会调用 `_recovery_refresh()` 补扫根目录和一级子目录。心跳刷新是低频兜底，不是实时主路径。

### 8.3 主窗口关闭顺序

保持以下顺序，不能把 `processEvents()` 提前：

1. 将 watcher 的所有回调设为 `None`。
2. 停止心跳并设置全局停止事件。
3. `NASWatcherManager.stop_all()`。
4. 安全处理残余 Qt 事件。
5. 停止中栏/右栏复制 Worker 和缩略图线程。
6. `WorkerManager.stop_all(timeout_per_worker=1500)`。

原因是队列中残留的 watcher 信号可能触发索引写入；如果先处理事件，关闭窗口会被 NAS/SQLite 操作拖住。

## 9. QC 检测管线

### 9.1 入口和窗口边界

```text
主窗口/文件右键
  -> MediaNexus.qc_bridge.open_qc_detection()
  -> FFmpegManager 可用性检查
  -> qc_gui.main_window.MainWindow
  -> DetectionThread
  -> core.engine.DetectionEngine
```

QC 窗口是独立非模态顶级窗口，引用保存在 `qc_bridge` 的列表中，销毁时移除。QC UI 由 `Toolbar`、`FilePanel`、`ResultPanel`、`DetailPanel`、`BottomBar`、`StatusBar` 组成；主题由 `ThemeManager` 统一应用。

QC 窗口默认 `1200x750`，最小 `1100x700`；主内容是横向 `[文件 | 结果 | 详情]` splitter。窗口尺寸必须有最小值和滚动容器，不能把固定内容挤出屏幕。

### 9.2 当前有效检测

`core.adapters.create_default_registry()` 当前注册三个检测器：

| key | 适配器 | 算法来源 |
| --- | --- | --- |
| `black_frame` | `BlackFrameAdapter` | 复用 `FrameScanner.thumbs` 的黑帧段检测 |
| `black_border` | `BlackBorderAdapter` | 读取 `FrameScanner` 在线计算的黑边结果 |
| `silence` | `SilenceAdapter` | FFmpeg 音频静音分析 |

其他 QC 能力：`VideoProbe` 提供元数据，`ConsistencyChecker` 做批量一致性，`core.multi_version_compare` 和对应对话框做多版本横向比较，`ExcelExporter` 输出报告。

`DetectionEngine.analyze_file()` 的顺序：

1. FFprobe 和 FrameScanner 并行启动。
2. FrameScanner 单次解码，生成缩略图并在线做黑边分析。
3. 根据 FFprobe 时长对缩略图按需降采样。
4. 静音检测与视觉检测并行。
5. 通过注册表运行黑帧/黑边，收集静音结果。
6. 计算综合状态；批量检测完成后做一致性校验。

### 9.3 已清理的 QC 占位

历史代码曾在结果、QC 结果树和 Excel 导出中预留 `flash_frame`，但仓库没有对应检测器、阈值或实现文件。本轮已删除这组占位，当前 QC 结果契约只包含实际运行的检测项。未来如果实现闪帧/夹帧检测，必须新增明确检测器、配置、测试和结果契约后再接入 UI。

## 10. UI 样式和窗口约束

主程序样式集中在 `MediaNexus/constants.py`，QC 样式集中在 `qc_gui/styles.py` 与 `qc_gui/theme.py`。维护 UI 时遵守：

- 所有滚动容器使用统一边界，隐藏 Qt 滚动条箭头和角落色块，`QAbstractScrollArea::corner` 保持透明。
- 普通边界使用 1px 中性色线；不要通过额外 wrapper、阴影或重复边框制造“主体外套一层”的效果。
- 菜单保持单层矩形边界，不在右下角添加装饰色块；状态栏禁用 QSizeGrip。
- 双索引主窗口只使用横向 splitter；QC 主窗口也只使用横向内容 splitter。
- 内容可能超出屏幕时用 `QScrollArea`、换行和合理最小尺寸解决，不能靠固定高度裁切文本或控件。
- `QPixmap` 不跨线程创建；主题切换后必须同步更新面板图标、下拉框、滚动容器和弹窗样式。
- 所有可交互控件必须保持可用尺寸和明确父级；新增样式后至少验证主窗口、设置、添加项目和 QC 四类窗口。

## 11. FFmpeg、依赖和构建

### 11.1 依赖职责

| 依赖 | 用途 |
| --- | --- |
| PySide6 | 主窗口、QC 窗口、WebEngine 手册回退 |
| rapidfuzz | 本地/服务器名称匹配 |
| aiofiles | NAS 异步目录扫描 |
| pywin32（Windows） | `ReadDirectoryChangesW`、剪贴板辅助 |
| opencv-python-headless | 视频帧读取和缩放 |
| numpy | QC 数值分析 |
| openpyxl | Excel 报告 |
| PyInstaller | onedir 打包 |

当前没有第二套 Qt GUI 框架；PyQt5/PyQt6 在 spec 中明确排除。`aiofiles`、`rapidfuzz`、OpenCV、NumPy 和 openpyxl 都有实际运行时调用，不能删除。

### 11.2 FFmpeg 路径优先级

1. 系统 `PATH`。
2. 主配置中的手动目录。
3. 打包/开发目录 `resources/ffmpeg`。
4. `%APPDATA%\MediaNexus\ffmpeg\bin`。

开发环境可执行：

```powershell
python scripts/fetch_ffmpeg.py
```

缺少 FFmpeg 时主程序仍可打开，但 QC 会在启动检测前提示下载或指定目录。

### 11.3 打包

```powershell
python -m PyInstaller MediaNexus.spec --clean --noconfirm
```

输出为 `dist/MediaNexus/`，模式是 `onedir`。安装器依赖完整的 `dist/MediaNexus/*`，再执行：

```powershell
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' installer\MediaNexus-Setup.iss
```

安装包输出文件名由 Inno Setup 的版本宏生成，例如 `dist/installer/MediaNexus-Setup-1.1.0.exe`。发布到 GitHub Release 时必须直接上传这个带 `.exe` 后缀的文件，不要上传无扩展名的重命名文件。

安装脚本中出现 `MediaSync` 仅用于清理历史安装注册表项，不代表当前产品名或当前模块。

## 12. 测试和发布前检查

### 12.1 基础检查

```powershell
python -m compileall -q MediaNexus core qc_gui utils scripts tests run.py
python -m pytest tests/ -q
python -m pip check
python -m ruff check MediaNexus core qc_gui utils scripts tests run.py --select F401,F841,F821,F811,F822,F823
git diff --check
```

### 12.2 按修改范围

| 修改范围 | 最低验证 |
| --- | --- |
| 配置、匹配、索引、Worker | `python -m pytest tests/ -q` |
| 文件列表、拖放、复制/移动 | 启动主程序，验证本地↔服务器同屏、跨栏复制、同栏移动、Ctrl/Shift 语义 |
| 设置、滚动容器、菜单、关于 | 验证所有选项卡和 100%/125% DPI 下窗口不裁切 |
| watcher、关闭流程 | `test_watcher_stop_does_not_hang` + 关闭主程序；验证断连/重连和溢出补扫 |
| QC 算法 | 合成检测器测试 + 真实样片的黑帧、黑边、静音和 Excel 导出 |
| 打包 | 启动 `dist/MediaNexus/MediaNexus.exe`，打开用户手册和 QC |
| 安装器 | 全新安装、覆盖升级、卸载；确认旧注册表清理不误删当前配置 |

### 12.3 UI 快速检查清单

- 主窗口双索引永远横向三栏；仅本地/仅服务器切换后无残余边框和空白占位。
- 设置、添加项目、QC 窗口的滚动条滚轮按像素滚动，不因下拉框/SpinBox 滚轮误改值。
- 滚动区域上下没有箭头小方块，右下角没有 QSizeGrip 或角落色块。
- 文件从服务器拖到本地可复制，从本地拖到服务器可复制，同栏拖入子文件夹可移动。
- 菜单、关于、用户手册弹窗尺寸合理，内容完整且控件可点击。
- QC 窗口主题、状态栏、结果树和主窗口样式一致；关闭 QC 不影响主窗口。

## 13. 修改指南和禁止事项

### 新增主程序功能

1. 先确定属于项目、索引、匹配、文件操作还是设置边界。
2. 阻塞 I/O 放进已有 Worker；不要在 QWidget slot 里直接扫描 NAS。
3. 持久化字段走 `config_manager`，并评估 schema 迁移。
4. 检查陈旧结果丢弃、signal 解绑、`closeEvent` 和窗口重新加载。
5. 双栏传输只扩展 `FileListView` 的原生拖放契约，不新增“发送到对侧”快捷通道。

### 新增 QC 检测

1. 在 `core/` 实现 `BaseDetector` 子类和明确的结果 dict。
2. 在 `core/adapters.py` 注册，说明是否复用 `FrameScanner.thumbs`。
3. 在 `utils/config.py` 增加默认阈值；如影响主配置则同步 schema 迁移。
4. 同步 `qc_gui` 结果树、异常详情、导出器和取消路径。
5. 在 `tests/test_detectors.py` 增加合成 fixture 测试。

### 禁止事项

- 不恢复 `qc_gui/preset_manager.py`、`logo/`、`presets/` 或旧 `ProjectSync_Studio` 包。
- 不把 `dist/`、`build/`、`data/`、日志和 `__pycache__` 当作源码提交。
- 不为了“看起来能用”删除配置迁移、旧文件迁移、旧缓存清理或安装器注册表清理。
- 不在 `core` 引入 PySide6，不在子线程创建 QPixmap，不跨线程共享 SQLite 写连接。
- 不用固定高度掩盖文字或控件；窗口必须有最小尺寸、滚动容器和可验证的缩放行为。

## 14. 接手项目的阅读顺序

1. `README.md`：功能和启动方式。
2. `MediaNexus/constants.py`：路径、默认值和主程序样式。
3. `MediaNexus/config_manager.py`、`models.py`：配置 schema 和项目契约。
4. `MediaNexus/ui/main_window.py`：三栏布局、模式切换、关闭顺序。
5. `MediaNexus/ui/file_list_view.py`：虚拟列表、拖放、剪贴板和刷新后的选中恢复。
6. `MediaNexus/indexer.py`、`watcher.py`：NAS 索引和实时变更。
7. `MediaNexus/workers.py`、`worker_manager.py`：后台任务生命周期。
8. `core/engine.py`、`base_detector.py`、`adapters.py`：QC 管线。
9. `qc_gui/main_window.py`、`qc_gui/widgets/`、`qc_gui/theme.py`：QC UI。
10. `utils/config.py`、`ffmpeg_manager.py`、`storage_manager.py`、`exporter.py`：QC 基础设施。
11. `tests/test_smoke.py`、`tests/test_detectors.py`：可执行契约。

最后更新本文前，先运行第 12 节命令，并重新核对目录树和审计结论；文档不应根据历史截图或已删除文件猜测当前结构。
