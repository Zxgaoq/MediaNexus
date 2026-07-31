# MediaNexus 开发手册

> 版本：v1.0.0  
> 更新时间：2026-07-28  
> 适用对象：后续维护者 / 功能开发者 / 问题排查者

---

## 1. 项目身份

| 项目 | 说明 |
| --- | --- |
| 产品名 | **MediaNexus** |
| 定位 | 本地项目与服务器素材的项目级同步管理，加视频 QC 检测与 Excel 报告导出 |
| 运行形态 | Windows 桌面应用，基于 PySide6 |
| 系统形态 | 单进程、模块化桌面单体 |
| 开发入口 | `run.py` |
| 打包入口 | `MediaNexus/main.py` |
| 主配置路径 | `%APPDATA%/MediaNexus/config.json` |
| 索引数据库 | `%APPDATA%/MediaNexus/nas_index.db` |
| 分发形态 | PyInstaller `onedir` + Inno Setup |

> 注意：旧目录 `%APPDATA%/MediaNexus` 仅用于自动迁移。当前新代码与新文档都应以 `%APPDATA%/MediaNexus/` 为准。

---

## 2. 架构决策

### ADR-001：采用模块化桌面单体

- **背景**：这是本地桌面工具，主要瓶颈是 NAS I/O、视频解码与 GUI 响应。
- **决策**：保持 PySide6 单进程应用，不拆成本地 HTTP 服务或多进程架构。
- **收益**：部署简单、离线可用、调试路径直接。
- **代价**：模块边界依赖代码纪律，线程安全要求更高。

### ADR-002：以服务器项目文件夹作为当前项目锚点

- **背景**：当前工作流以服务器素材目录为项目发现入口，再匹配本地目录。
- **决策**：项目内部继续复用历史字段 `local_name` 作为唯一键，但它通常是服务器路径。
- **收益**：兼容旧字段名并适配服务器优先工作流。
- **代价**：字段名具有误导性，新代码必须明确区分 key 与显示名。

### ADR-003：使用 JSON 配置 + SQLite 索引

- **背景**：需要本地可读配置，同时提升 NAS 浏览性能。
- **决策**：配置用 JSON，服务器索引用 `nas_index.db`。
- **收益**：易排查、易迁移、本地性能更稳定。
- **代价**：要处理 schema 兼容和 SQLite 线程边界。

### ADR-004：QC 视觉检测共享一次视频解码

- **背景**：黑帧、黑边都需要读帧，重复解码成本高。
- **决策**：由 `FrameScanner` 单次解码并将结果复用于多个检测器。
- **收益**：显著降低长视频检测成本。
- **代价**：`DetectionEngine` 与 `FrameScanner` 接口变得关键，新检测项应优先复用该管线。

### ADR-005：配置 schema 版本化迁移

- **背景**：配置字段随版本增长，靠散落的 `if key not in data` 做兼容容易遗漏。
- **决策**：引入 `CURRENT_SCHEMA_VERSION` + `MIGRATIONS` 字典，每个版本对应一个迁移函数，`load()` 时自动链式升级。
- **收益**：新增字段只需写一个迁移函数，不再散落 ad-hoc 代码；版本可追踪。
- **代价**：每次 schema 变更必须同时写迁移函数并递增版本号。

### ADR-006：QC 检测器插件化注册表

- **背景**：新增检测项需要改 engine / config / gui / exporter 五处，扩展成本高。
- **决策**：定义 `BaseDetector` 统一接口 + `DetectionContext` 上下文 + `DetectorRegistry` 注册表，`DetectionEngine` 通过注册表遍历调用。黑边检测仍内联于 `FrameScanner.scan()`（保留 ADR-004），通过 `BlackBorderAdapter` 从 scanner 提取结果。
- **收益**：新增检测项只需一个文件 + 一行注册；engine / gui / exporter 不需要为新检测器改动。
- **代价**：引入了 adapter 层；黑边检测的注册是提取模式而非独立运行。

### ADR-007：实时文件监控（与资源管理器同机制）

- **背景**：服务器面板加载依赖手动刷新或心跳定时器，用户期望文件变更（创建/删除/重命名/内容保存）能实时反映在界面上，体验与 Windows 资源管理器一致。
- **决策**：使用 Windows `ReadDirectoryChangesW` API（与资源管理器相同机制）通过 pywin32 递归监控 NAS 目录。每个已确认项目对应一个 `NASWatchThread`（QThread），事件经 500ms 防抖窗口合并后触发增量索引更新（`refresh_dir`：单级 scandir + diff + 单事务写入），受影响的面板同步从索引读取并刷新（不再经过 ListWorker 线程）。
- **线程架构**：阻塞的 `ReadDirectoryChangesW` 跑在 daemon 子线程中，通过 `queue.Queue` 回传事件；QThread 以 300ms 超时轮询 queue 做防抖和信号发射。**原因**：`ReadDirectoryChangesW` 是同步阻塞调用且无超时参数，在 NAS/SMB 路径上从另一线程 `CloseHandle` 不能可靠中断它。若 QThread 直接执行该调用，`stop()` 后线程可能永远卡死，导致进程无法关闭。daemon 线程方案下 QThread 在 300ms 内退出，daemon 线程随进程消亡。
- **收益**：文件变更在 1 秒内反映到界面；增量更新只扫描受影响目录（百毫秒级）；连接断开自动重连，重连后补偿刷新补扫丢失事件；关闭时不卡死。
- **代价**：依赖 pywin32（已在 requirements.txt）；需要处理缓冲区溢出（事件过多时丢失）和 NAS 断连恢复；daemon 线程在进程退出前可能仍阻塞（无害，随进程消亡）。

### ADR-008：QC 检测管线并行调度

- **背景**：`analyze_file` 原为全串行链：FFprobe → FrameScanner → 黑帧 → 黑边 → 静音。FFprobe（子进程）和 FrameScanner（OpenCV 解码）读同一文件但互不依赖，静音检测只需文件路径不依赖缩略图，三者无需串行等待。
- **决策**：
  1. FFprobe 与 FrameScanner 通过 `ThreadPoolExecutor(max_workers=2)` 并行启动。FrameScanner 从 OpenCV 自行获取时长并计算 `sample_interval`，解除对 FFprobe `duration` 的前置依赖。
  2. 静音检测在视觉管线启动前异步提交（`ThreadPoolExecutor(max_workers=1)`），与黑帧/黑边检测并行执行，视觉检测器循环中跳过 `silence` key，最后收集结果。
  3. `actual_fps` 优先从 FFprobe 元数据获取（精度更高），fallback 到 `scanner.fps`；`duration` 优先从 FFprobe 元数据获取（精度更高），fallback 到 `scanner.duration`（OpenCV 提供）。
- **收益**：FFprobe 耗时（0.5~2s）被 FrameScanner 解码吸收；静音检测耗时（视频时长 10~20%）被视觉管线覆盖；单文件总耗时从"各环节之和"降为"最长环节耗时"，预估降低 30~50%。
- **代价**：增加了线程管理复杂度；取消检测时需要额外清理静音 future 和 executor。
- **不变项**：各检测器的算法逻辑、输入数据、阈值参数、分辨率均未改变；注册表仍包含 3 个适配器（SilenceAdapter 在循环中被 skip 但不移除，保持注册表完整性）。

---

## 3. 模块边界

| 模块 | 职责 |
| --- | --- |
| `MediaNexus` | 主程序、项目列表、设置、服务器索引、匹配、文件浏览、启动链路 |
| `core` | 无 GUI 依赖的 QC 核心算法与检测编排 |
| `qc_gui` | QC 独立窗口、结果展示、交互控件 |
| `utils` | FFmpeg 管理、配置代理、Excel 导出、缓存与文档查看 |

### 边界规则

- `core/` 不应 import PySide6，也不应直接弹窗
- `qc_gui/` 应通过 `utils.config` 访问 QC 配置，不要私自维护第二份配置源
- UI 层可以做编排，但耗时 I/O 必须交给 Worker
- `MediaNexus/config_manager.py` 是主配置唯一权威来源
- `NASIndexer` 的写入必须串行化，读取必须通过只读连接

---

## 4. 启动与运行

### 开发启动

```bash
python -m pip install -r requirements.txt
python run.py
python -m MediaNexus.main
```

### 启动链路

```text
run.py
  -> 安装 crash_handler
  -> import MediaNexus.main.main
  -> 切换工作目录到项目根
  -> 调用包入口

MediaNexus.main.main()
  -> 再次安装 crash_handler
  -> 调用 MediaNexus.ui.main_window.run_app()
  -> 创建 QApplication 并显示主窗口
```

### 重要说明

- `run.py` 是开发启动器
- PyInstaller 直接使用 `MediaNexus/main.py`
- 启动级保护不能只写在 `run.py`，必须在包入口也覆盖

---

## 5. 目录结构

```text
MediaNexus/
├── run.py                         开发启动器
├── README.md                      项目说明
├── requirements.txt               依赖清单
├── config.json                    默认配置模板
├── build.bat                      打包脚本
├── MediaNexus.spec        PyInstaller onedir 配置
├── .gitignore
├── MediaNexus/            主程序包
│   ├── __init__.py
│   ├── main.py                    PyInstaller 入口
│   ├── constants.py               常量、路径、状态、样式
│   ├── config_manager.py          主配置单例 + schema 迁移链
│   ├── models.py                  Project dataclass 类型化模型
│   ├── worker_manager.py          Worker 统一管理器（注册/停止/generation）
│   ├── watcher.py                 NAS 实时监控（ReadDirectoryChangesW + 防抖）
│   ├── crash_handler.py           崩溃捕获与日志
│   ├── indexer.py                 服务器索引器（含结构化日志）
│   ├── matcher.py                 匹配逻辑
│   ├── workers.py                 QThread 后台任务
│   ├── qc_bridge.py               打开 QC / 多版本窗口
│   ├── clipboard.py               剪贴板模块
│   ├── utils.py                   主程序工具模块
│   └── ui/                        三栏主窗口与对话框
│       ├── __init__.py
│       ├── main_window.py         主窗口（含 closeEvent 六步）
│       ├── left_sidebar.py        左栏：项目导航
│       ├── middle_panel.py        中栏：本地目录
│       ├── right_panel.py         右栏：服务器目录
│       ├── file_list_view.py      文件列表（虚拟滚动 + 选中保持）
│       ├── add_project_dialog.py  添加项目对话框
│       ├── select_match_dialog.py 选择匹配候选对话框
│       ├── settings_dialog.py     设置对话框
│       ├── preset_panel.py        预设面板
│       └── widgets.py             通用控件
├── core/                          QC 领域核心（禁止依赖 PySide6）
│   ├── __init__.py
│   ├── engine.py                  检测引擎（注册表驱动 + 并行调度）
│   ├── base_detector.py           BaseDetector 接口 + DetectionContext + DetectorRegistry
│   ├── adapters.py                检测器适配器 + create_default_registry()
│   ├── frame_scanner.py           单次解码扫描
│   ├── black_frame.py             黑帧检测
│   ├── black_border.py            黑边检测
│   ├── silence_detect.py          静音检测
│   ├── video_probe.py             FFprobe 元数据
│   ├── consistency.py             一致性校验
│   └── multi_version_compare.py   多版本对比
├── qc_gui/                        QC 窗口组件
│   ├── __init__.py
│   ├── main_window.py             QC 主窗口（多版本对比 Tab）
│   ├── multi_version_compare_dialog.py  多版本对比对话框
│   ├── preset_manager.py          预设管理
│   ├── styles.py                  QC 样式
│   ├── theme.py                   主题
│   └── widgets/                   QC 子控件
│       ├── __init__.py
│       ├── toolbar.py             工具栏
│       ├── file_panel.py          文件面板
│       ├── result_panel.py        结果面板
│       ├── detail_panel.py        详情面板
│       ├── bottom_bar.py          底栏
│       └── status_bar.py          状态栏
├── utils/                         基础设施与配置代理
│   ├── __init__.py
│   ├── config.py                  QC ConfigManager（复用主程序配置，独立运行回退本地）
│   ├── ffmpeg_manager.py          FFmpeg 路径与可用性管理
│   ├── storage_manager.py         存储路径管理
│   ├── exporter.py                Excel 报告导出
│   ├── docs_viewer.py             文档查看器
│   └── onboarding.py              首次启动引导
├── assets/                        图标与静态资源
│   ├── logo.png
│   ├── logo.ico
│   └── arrows/                    SpinBox 箭头 SVG（运行时复制到临时目录）
│       ├── spin_up.svg
│       └── spin_down.svg
├── logo/                          品牌资源
│   └── 透明版.png
├── docs/
│   └── MediaNexus-Manual.html     用户手册
├── dev/
│   └── DevHandbook.md             Markdown 开发手册（本文件）
├── scripts/
│   └── fetch_ffmpeg.py            FFmpeg 下载脚本
├── installer/                     Inno Setup 安装脚本
│   ├── MediaNexus-Setup.iss
│   └── build-installer.bat
├── resources/ffmpeg/              内置 ffmpeg / ffprobe（由 scripts/fetch_ffmpeg.py 下载）
└── tests/
    ├── test_smoke.py              冒烟测试
    └── test_detectors.py          检测器单元测试（合成 fixture）
```

---

## 6. 核心数据流

### 6.1 项目添加与匹配

```text
设置本地根目录 / 服务器根目录
  -> 扫描服务器
  -> IndexWorker(fast=True)
  -> NASIndexer.rebuild(...)
  -> 左栏添加项目
  -> AddProjectDialog 生成候选
  -> config_manager.upsert_project(project)
  -> DeepScanWorker 递归补全索引
  -> MatchWorker 维护 local_path / nas_candidates / status
```

> 当前项目模型的锚点是服务器项目路径。`project["local_name"]` 当前是内部唯一键，通常等于 `confirmed_nas_path`，不要把它当作显示名。

### 6.2 主界面浏览

```text
LeftSidebar 选择项目 key
  -> MainWindow._on_project_selected(key)
  -> config_manager.get_project(key)
  -> MiddlePanel.load(local_path, ...)
  -> RightPanel.load(project)
  -> ListWorker 优先读索引，必要时实时扫描
```

### 6.3 文件操作

```text
FileListView 选择 / 拖拽 / 右键
  -> 计算目标目录
  -> check_overwrite_conflicts()
  -> CopyWorker / MoveWorker
  -> refresh_current()
```

### 6.4 实时文件监控（ADR-007）

```text
MainWindow._start_watching_projects()
  -> NASWatcherManager.watch(confirmed_nas_path)  ← 每个已确认项目一个 NASWatchThread
  -> NASWatchThread.run()
     -> 启动 daemon 子线程 _blocking_reader()
        -> win32file.CreateFile(dir, FILE_FLAG_BACKUP_SEMANTICS)
        -> 循环 ReadDirectoryChangesW(recursive=True)  ← 阻塞，由 daemon 线程承担
        -> 事件通过 queue.Queue 回传
     -> QThread 以 300ms 超时轮询 queue
     -> 事件收集 + 500ms 防抖
     -> changed.emit(root, [affected_dirs])

MainWindow._on_watcher_changed(root, affected_dirs)
  -> NASIndexer.refresh_dirs(affected_dirs)
     -> 逐目录: os.scandir(dir) → diff → INSERT/UPDATE/DELETE
  -> 判断受影响面板 → 同步从索引读取 list_children() → 直接更新视图
     （不再经过 ListWorker 线程，避免"访问服务器"转圈）

刷新按钮（RightPanel._refresh）双路策略：
  watcher 活跃 → refresh_dir(当前目录) + 同步读索引（百毫秒级，无转圈）
  watcher 未活跃 → 回退到旧的 RefreshIndexWorker 子树扫描

心跳定时器（角色已降级）：
  watcher 是主力实时机制；心跳仅作低频兜底校验（建议 3~5 分钟间隔），
  用于补偿 watcher 断连/溢出期间可能遗漏的深层变更。

断连恢复：
  disconnected → _disconnected_roots.add(root)
  reconnected  → _recovery_refresh(root)  ← 扫描一级子目录补偿丢失事件

缓冲区溢出：
  ReadDirectoryChangesW 返回空列表 → overflow.emit(root)
  -> _recovery_refresh(root)
```

### 6.5 QC 检测

```text
qc_bridge.open_qc_detection(file_paths, thread_count)
  -> FFmpegManager 可用性检查
  -> QCMainWindow
  -> DetectionThread
  -> DetectionEngine.analyze_batch()
     -> analyze_file(filepath)
        -> ┌─ 并行阶段（ThreadPoolExecutor, ADR-008）─┐
           │  probe_future = VideoProbe.probe()         │
           │  scan_future  = FrameScanner.scan(         │
           │      bb_detector, sample_interval=None)    │
           │    ← scanner 从 OpenCV 自行计算采样间隔    │
           │    ← 黑边在此内联完成（ADR-004）           │
           └────────────────────────────────────────────┘
        -> 等待 probe_future → metadata
        -> 等待 scan_future  → thumbs + black_border_result
        -> 根据 FFprobe 精确时长重算 sample_interval，对 thumbs 按需降采样
        -> 静音检测异步启动（silence_executor）
        -> 构建 DetectionContext
        -> 遍历 DetectorRegistry（跳过 silence）：
           BlackFrameAdapter.detect(ctx)   ← 纯内存
           BlackBorderAdapter.detect(ctx)  ← 从 scanner 提取
        -> 收集 silence_future.result()
        -> _determine_overall()
     -> ConsistencyChecker.check_against_baseline()
  -> ExcelExporter.export()
```

---

## 7. 数据契约

### 7.1 主配置 JSON

主配置路径：`%APPDATA%/MediaNexus/config.json`

关键字段：

- `local_roots`
- `nas_roots`
- `projects`
- `settings`
- `qc_presets`
- `qc_active_preset`
- `qc_settings`
- `indexed_at`

### 7.2 项目字段说明

| 字段 | 含义 | 注意 |
| --- | --- | --- |
| `local_name` | 历史字段名，当前更接近内部唯一键 | 通常等于服务器路径，不用于展示 |
| `name` | 项目显示名 | 重命名只改配置，不改磁盘目录 |
| `local_path` | 本地目录 | 可为空 |
| `confirmed_nas_path` | 已确认服务器目录 | 右栏以此为根加载 |
| `status` | `matched` / `pending` / `unmatched` / `none` | 表示匹配状态 |

### 7.3 NAS 索引 SQLite

- 数据库：`nas_index.db`
- 主要表：`entries`、`meta`
- 连接策略：
  - 写入连接由单例持有
  - 读取必须通过 `_open_ro()` 新建只读连接
  - 写入通过 `_write_serial` 串行化

---

## 8. 主程序速查

### `constants.py`

- `APP_NAME = "影枢"`
- `APP_VERSION = "1.0.0"`
- `CONFIG_DIR = Path(APPDATA) / "MediaNexus"`
- `INDEX_DB_PATH = CONFIG_DIR / "nas_index.db"`
- `DEFAULT_MATCH_THRESHOLD = 80`
- `PAGE_SIZE = 500`
- `MAX_CONCURRENCY = 4`

### `config_manager.py`

> **注意：项目中有两个 `ConfigManager`**，不要混淆：
> - `MediaNexus/config_manager.py` 的 `ConfigManager`（本节）—— 主程序配置单例，权威来源，管 projects / settings / qc_presets / qc_active_preset / qc_settings 等，全局实例 `config_manager`。
> - `utils/config.py` 的 `ConfigManager` —— QC 子系统专用，加载时优先复用主程序配置（通过 `_resolve_host_config_manager()` 拿到主程序单例的 qc_* 字段），独立运行 QC（未加载主程序）时回退到本地 `config.json`。保存时也走主程序单例统一落盘，避免双源漂移。

- `CURRENT_SCHEMA_VERSION = 2`
- `MIGRATIONS` — 版本迁移函数映射（v0→v1, v1→v2, ...）
- `_run_migrations(data)` — load() 时自动链式升级
- 属性：`data` / `local_roots` / `nas_roots` / `projects` / `settings` / `project_mode` / `qc_presets` / `qc_active_preset` / `qc_settings` / `onboarding_done` / `auto_refresh_enabled` / `auto_refresh_interval` / `match_threshold` / `ignore_patterns` / `ffmpeg_manual_dir` / `ffmpeg_download_url`
- `get_project(local_name)` — 按 key 取项目 dict
- `upsert_project(project)` — 写入前通过 `Project.from_dict()` 做边界校验
- `remove_project(local_name)` — 删除项目并清理 excluded 列表
- `cleanup_stale_projects()` — 清理 confirmed_nas_path 已失效的非 UNC 项目
- `set_confirmed_nas(local_name, nas_path)` — 确认服务器路径绑定
- `set_indexed_at(iso)` — 记录最近一次索引时间
- 全局单例：`config_manager`

### `models.py`

- `Project` — dataclass，替代裸 dict 访问
  - `from_dict(data)` / `to_dict()` — 与配置 dict 互转
  - `merge_dict(data)` — 增量更新
  - `display_name` — 显示名属性（优先 name，fallback 路径末段）
  - `__post_init__` 校验 `local_name` 非空、`status` 合法

### `worker_manager.py`

- `WorkerManager` — Worker 生命周期统一管理器
  - `register(name, worker)` / `unregister(name)` / `get(name)` — 注册/注销/查询
  - `stop_all(timeout_per_worker)` — 并行发信号 + 逐个等待（含 `isRunning()` 的 RuntimeError 防护）

### `indexer.py`

- `NASIndexer.rebuild(...)` — 全量重建（`fast=True` 仅扫项目级目录）
- `NASIndexer.reindex_subtree(root)` — 增量重建单个子树
- `NASIndexer.refresh_dir(dir_path)` — 单级增量刷新（scandir + diff + 单事务增删改），由 watcher 事件驱动；写锁超时 2s，全量扫描期间自动跳过
- `NASIndexer.refresh_dirs(dir_paths)` — 批量增量刷新多个目录
- `NASIndexer.query_all_folders()` — 返回所有已索引文件夹路径（匹配候选用）
- `NASIndexer.get_folder_mtime(path, default=0.0)` — 取某文件夹自身 mtime（项目排序用）
- `NASIndexer.list_children(parent_path)` — 直接子项（文件夹在前、按名称排序），供右栏懒加载
- 全局单例：`indexer`

### `watcher.py`

- `NASWatchThread(QThread)` — 单目录实时监控线程
  - **架构**：阻塞的 `ReadDirectoryChangesW` 跑在 daemon 子线程（`_blocking_reader`），通过 `queue.Queue` 回传事件；QThread 以 `POLL_TIMEOUT`（300ms）超时轮询 queue，做防抖和信号发射。`stop()` 后 QThread 在 300ms 内退出，daemon 线程随进程消亡。
  - 使用 `ReadDirectoryChangesW` 递归监控（与资源管理器相同 API）
  - `WATCH_FLAGS`: 文件名 / 目录名 / 大小 / 最后写入 / 创建时间
  - `DEBOUNCE_INTERVAL = 0.5s` — 防抖合并批量事件
  - `RECONNECT_INTERVAL = 5.0s` — 断连自动重连间隔（短间隔循环检查 stop_event）
  - `POLL_TIMEOUT = 0.3s` — QThread 轮询 queue 的超时，决定 stop() 后最大退出延迟
  - `BUFFER_SIZE = 65536` — 64KB 事件缓冲区
  - Signals: `changed(str, list)` / `error(str, str)` / `connected(str)` / `disconnected(str)` / `overflow(str)`
- `NASWatcherManager` — 多目录监控生命周期管理
  - `watch(root_path)` / `unwatch(root_path)` / `stop_all()` / `watching_roots()`
  - `stop_all()` 策略：并行发 stop 信号 → 统一等待（每个最多 1s）→ 清空字典
  - 回调: `on_changed` / `on_connected` / `on_disconnected` / `on_error` / `on_overflow`
  - **关闭时**：`closeEvent` 先将所有回调设为 `None`（防止队列信号触发耗时操作），再调 `stop_all()`

### `workers.py`

- `IndexWorker`
- `RefreshIndexWorker`
- `DeepScanWorker`
- `MatchWorker`
- `ListWorker`
- `CopyWorker`
- `MoveWorker`

---

## 9. QC 引擎速查

### `DetectionEngine`

- `analyze_file(filepath, fps=None)` — 每次完整检测，无缓存；内部采用并行调度（ADR-008）：FFprobe 与 FrameScanner 并行，静音检测与视觉检测器并行
- `analyze_batch(file_list, fps=None, max_workers=None)`
- `cancel()`
- `validate_environment()`
- `_registry` — `DetectorRegistry` 实例，引擎通过注册表遍历调用检测器（静音在循环中被 skip，单独异步收集）

### `BaseDetector` / `DetectorRegistry`

- `BaseDetector` — 所有检测器必须实现的抽象基类
  - `key` — 结果 dict 中的字段名
  - `detect(ctx: DetectionContext) -> dict` — 检测入口
- `DetectionContext` — 传递给每个检测器的上下文，字段：`filepath`（视频路径，静音检测用）、`metadata`（FFprobe 元数据）、`fps`（帧率）、`thumbs`（缩略图列表 `[(frame_num, gray_160x90), ...]`）、`scanner`（FrameScanner 引用，黑边检测用）、`thresholds`（当前预设阈值）、`performance`（性能设置）
- `DetectorRegistry` — 检测器注册表
  - `register(detector)` / `iterate()`
- `adapters.create_default_registry()` — 返回包含 3 个内置适配器的注册表

### 单项检测器

| 检测项 | 文件 | 说明 |
| --- | --- | --- |
| 元数据 | `video_probe.py` | FFprobe JSON 探测 |
| 帧扫描 | `frame_scanner.py` | 单次解码 + 缩略图 + 在线黑边检测；`sample_interval=None` 时自动根据时长计算采样间隔 |
| 黑帧 | `black_frame.py` | 基于缩略图阈值与连续段；v2 转场识别（渐变 = 转场，骤变 = 错误/警告/高危 人工复核）；输出含 `frame_count` 字段（持续帧数），GUI 优先显示帧数而非秒数 |
| 黑边 | `black_border.py` | 悬崖探测 + 区域统计 + 众数过滤 |
| 静音 | `silence_detect.py` | FFmpeg silencedetect / librosa fallback |
| 一致性 | `consistency.py` | 多文件参数对比 |
| 多版本 | `multi_version_compare.py` | 多文件夹横向比较 |

> 新增视觉检测项时，优先复用 `FrameScanner.thumbs`，不要重新全量解码视频。

---

## 10. 线程与并发

### 规则

- GUI 主线程只负责界面响应和 UI 更新
- 目录读取、索引重建、复制移动、视频检测必须放到 Worker 线程
- `QPixmap` 不能在子线程创建；子线程只生成 `QImage`
- SQLite 连接不能跨线程随意复用
- 新增后台任务时，必须在 `WorkerManager` 中注册，确保 `closeEvent` 能自动停止
- `closeEvent` 通过 `WorkerManager.stop_all()` 统一停止所有 Worker（并行发信号 + 逐个等待）
- `NASWatchThread` 独立于 `WorkerManager` 管理（由 `NASWatcherManager` 管理生命周期），`closeEvent` 中通过 `_watcher.stop_all()` 单独停止
- `refresh_dir` 使用独立的短生命周期 SQLite 连接 + `_write_serial` 锁（2s 超时），全量扫描在跑时自动跳过增量更新
- **NAS 阻塞调用警告**：`ReadDirectoryChangesW` 在 NAS/SMB 路径上可能无限期阻塞，且 `CloseHandle` 不能可靠中断。任何包含该调用的线程必须设计为可放弃（daemon 线程），不能让它阻塞 QThread 或主线程的退出

### closeEvent 六步顺序（不可调换）

```text
1. 断开 watcher 全部回调（on_changed = None 等）
   → 防止队列中残留的 watcher 信号在后续 processEvents 中触发 refresh_dirs 等耗时操作
2. 停止心跳定时器 + 设置全局 stop_event
3. _watcher.stop_all()
   → QThread ~300ms 退出，daemon 读取线程随进程消亡
4. QApplication.processEvents()
   → 处理残余 UI 事件（此时 watcher 回调已断开，安全）
5. 停止面板内 copy worker + 缩略图线程
6. WorkerManager.stop_all(timeout_per_worker=1500)
```

> **教训**：若 `processEvents()` 在断开回调之前执行，队列中的 watcher 信号会触发 `refresh_dirs`（可能阻塞 2s 等写锁）和面板更新，导致关闭卡死。

### 典型风险

- 多个索引写任务并发造成数据库锁竞争
- 子线程直接操作 QWidget / QPixmap 导致崩溃
- watcher daemon 线程在 NAS 断连时可能长时间阻塞在 `ReadDirectoryChangesW` 中（无害但不可中断，进程退出时自动清理）
- `closeEvent` 中若 watcher 回调未断开就 `processEvents()`，队列信号触发 `refresh_dirs` 阻塞主线程

---

## 11. FFmpeg 集成

### 路径优先级

1. 系统 PATH
2. 用户手动指定目录
3. `resources/ffmpeg`
4. `%APPDATA%/MediaNexus/ffmpeg/bin`

### 关键接口

- `FFmpegManager().is_available`
- `FFmpegManager().ffmpeg_path`
- `FFmpegManager().ffprobe_path`
- `FFmpegManager().verify()`
- `FFmpegManager().set_manual_dir(path)`
- `FFmpegManager().ensure_ffmpeg(...)`

### 维护建议

- 发布时优先随包内置 FFmpeg
- QC 打不开时先检查 FFmpeg 可用性，而不是直接怀疑检测器逻辑

---

## 12. 构建与发布

### PyInstaller

```bash
python -m PyInstaller MediaNexus.spec --clean --noconfirm
```

输出目录：`dist/MediaNexus/`

### Inno Setup

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\MediaNexus-Setup.iss
```

安装器输出：`dist/installer/MediaNexus-Setup.exe`

#### 旧版注册表自动清理

安装脚本 `[Code]` 段内置 `CleanOldMediaSyncEntries` 过程，在 `InitializeWizard` 时自动运行：

1. 检测并卸载旧版 MediaSync（正确键名 + 错误键名），调用其 `unins*.exe /VERYSILENT`
2. 若卸载程序未能删除注册表键，则强制 `RegDeleteKeyIncludingSubkeys`

**历史 bug**：1.2 版安装脚本在 `[Code]` 中构造 `GetUninstallKeyName` 时多了一个 `}`，导致该版条目写入了 `{{GUID}}_is1`（双括号）而非正确的 `{{GUID}_is1}`。后续版本用正确键名检索时找不到 1.2 的条目，Windows「应用和功能」列表因此出现重复项。`BuggyKeyName` 常量专门用于定位该残留键。

### 发布注意事项

- 当前是 **onedir**，不是单文件 exe
- 用户配置与缓存保留在 `%APPDATA%/MediaNexus`
- 打包验证属于发布链路，不是每次功能修改都必须执行

---

## 13. 测试与验证

### 冒烟测试

```bash
python -m pytest tests/ -q
```

覆盖范围：

- 版本契约
- 默认忽略词
- 索引器重建和子项访问
- 并发写稳定性
- 只读连接隔离
- 增量刷新（`refresh_dir`）：新增文件检测 / 删除文件检测 / 文件修改检测 / 批量刷新 / 目录删除子树清除
- watcher 停止速度：`stop()` 后 QThread 应在 1.5s 内退出（验证 daemon 线程架构不阻塞关闭）
- matcher 归一化与评分
- FFmpegManager 接口行为

### 检测器单元测试

```bash
python -m pytest tests/test_detectors.py -v
```

覆盖范围（使用合成 numpy 缩略图，无需真实视频）：

- 黑帧检测：无黑帧 / 连续黑段 / 长段错误级 / 短段过滤 / 多段 / 阈值边界 / 转场识别
- 黑边检测：默认初始化 / 自定义参数 / 单帧无黑边
- Project 模型：校验 / display_name / roundtrip / merge

### 修改后的最小验证建议

| 修改范围 | 最低验证 |
| --- | --- |
| 配置 / 匹配 / 索引 / FFmpeg | `pytest tests/ -q` |
| UI 文件浏览 / 拖拽 / 删除 / 重命名 | `python run.py` 手测 |
| QC 检测器 | 用样片验证黑帧 / 黑边 / 静音 |
| watcher / 实时监控 / closeEvent | `pytest tests/test_smoke.py::test_watcher_stop_does_not_hang -v` + 手测关闭不卡死 |
| 打包配置 | 启动 `dist/MediaNexus/MediaNexus.exe` |
| 安装器 | 安装、升级、卸载验证 |

---

## 14. 修改指南

### 新增主程序功能

1. 先判断功能属于哪个边界：项目导航 / 本地文件 / 服务器文件 / 设置 / 后台任务
2. 有阻塞风险就加 Worker，不要直接写在 slot 里
3. 需要持久化时优先通过 `config_manager` 扩展字段
4. 同步检查 `closeEvent`、信号解绑与陈旧结果丢弃逻辑

### 新增 QC 检测项

1. 在 `core/` 下新建文件，实现 `BaseDetector` 子类（定义 `key`、`name`、`detect(ctx)`）
2. 在 `core/adapters.py` 中创建适配器（从 `DetectionContext` 提取所需数据）
3. 在 `create_default_registry()` 中注册一行
4. 阈值补到 `utils/config.py` 的 `DEFAULT_THRESHOLDS`（该字典目前包含 4 个分组：`black_frame` / `black_border` / `silence` / `performance`，其中 `performance` 含 `max_threads`、`max_duration_for_full_scan`）
5. 若需要配置 schema 变更，在 `config_manager.py` 的 `MIGRATIONS` 中加迁移函数并递增 `CURRENT_SCHEMA_VERSION`
6. 必要时同步修改 `qc_gui` 结果展示与 `utils/exporter.py`
7. 在 `tests/test_detectors.py` 中添加单元测试（合成 numpy 缩略图，无需真实视频）

> 新检测项应优先复用 `FrameScanner.thumbs`（ADR-004），在适配器中通过 `ctx.thumbs` 获取即可。

### 修改配置 schema

1. 在 `ConfigManager._default()` 中补默认值
2. 在 `MIGRATIONS` 中新增迁移函数（从当前版本升级到新版本）
3. 递增 `CURRENT_SCHEMA_VERSION`
4. `load()` 会自动运行迁移链，不要破坏已有用户值
5. setter 应保持即时落盘语义

### 修改 watcher / 实时监控

1. **不要在 QThread 中直接调用 `ReadDirectoryChangesW`**——NAS 路径上该调用可能无限期阻塞且无法中断。阻塞调用只能在 daemon 线程中执行
2. 修改 `NASWatchThread.run()` 时保持 queue 轮询模式，`POLL_TIMEOUT` 不要设太大（影响 stop 响应速度）
3. 修改 `closeEvent` 时保持六步顺序：断开回调 → 停心跳 → 停 watcher → processEvents → 停面板 worker → 停 WorkerManager
4. 新增 watcher 回调时，必须在 `closeEvent` 第一步中将其设为 `None`
5. 修改右栏 `_refresh()` 时保留 watcher 活跃 / 未活跃的双路判断
6. 心跳定时器已降级为兜底机制，不要将其作为主力刷新手段

---

## 15. 常见陷阱

1. `local_name` 不是显示名（用 `Project.display_name` 获取显示名）
2. README 可能出现旧配置路径或旧分发说明
3. 子线程共用 SQLite 连接会出问题
4. `QPixmap` 不能在子线程创建
5. 根目录 `config.json` 不是主配置权威来源
6. QC 结果每次都是实时检测，不再缓存。`storage_manager.py` 仍保留对旧 `qc_cache.db` 文件的清理能力（供用户清理历史残留）
7. 切换 `project_mode` 会清空项目列表，改逻辑时不能丢掉确认保护
8. 修改配置 schema 时必须同步写迁移函数并递增 `CURRENT_SCHEMA_VERSION`，不能只加默认值
9. 新增 Worker 时必须在 `WorkerManager` 中注册，确保 `closeEvent` 能正确停止
10. `ReadDirectoryChangesW` 返回空列表表示缓冲区溢出（事件丢失），不是"没有变更"
11. NAS 断连后 watcher 自动重连，但断连期间的事件会丢失，需通过 `_recovery_refresh` 补偿
12. `refresh_dir` 的 `_write_serial` 锁超时设为 2s，全量索引期间增量更新会被跳过（不影响正确性）
13. **`CloseHandle` 不能可靠中断 NAS 上阻塞的 `ReadDirectoryChangesW`**——这是 watcher 必须用 daemon 线程 + queue 架构的根本原因。不要试图在 QThread 中直接调用 `ReadDirectoryChangesW`
14. **`closeEvent` 必须先断开 watcher 回调再 `processEvents()`**——否则队列中的 watcher 信号会触发 `refresh_dirs`（阻塞等写锁）和面板更新，导致关闭卡死
15. 右栏「刷新」按钮在 watcher 活跃时走轻量路径（`refresh_dir` + 同步读索引），不活跃时回退子树扫描。修改刷新逻辑时必须保留这个双路判断
16. **QC 静音检测在注册表循环中被 skip，单独异步执行（ADR-008）**——新增检测器如果也需要与视觉管线并行（只依赖文件路径，不依赖缩略图），需要在 `analyze_file` 中类似静音检测的方式单独处理，不要仅注册到 registry 就期望它自动并行
17. **QC 取消检测时必须清理静音 future 和 executor**——`cancel()` 设置 `_cancel_flag` 后，`analyze_file` 在循环中退出时会对 `silence_future.cancel()` 和 `silence_executor.shutdown(wait=False)`。新增的异步检测器也必须在取消路径中做同样清理
18. **黑帧 severity 有四种：错误 / 警告 / 高危 人工复核 / 转场**——最低级从旧的"提示"改为"高危 人工复核"；当 `is_transition=True`（亮度曲线呈渐变转场特征）时 severity 为"转场"。黑帧输出新增 `frame_count` 字段（持续帧数），GUI 显示帧数而非秒数（避免短黑帧显示"0.0s"不可读）
19. **`utils/logger.py` 和 `presets/` 目录已删除**——`logger.py` 从未被引用（项目直接用标准 `logging.getLogger()`）；`presets/` 为空包。清理时同步移除了大量无用 import（详见各文件 git 历史）
20. **PySide6 Worker 使用 `deleteLater` 后必须清理 Python 引用**——`DeepScanWorker` 在 `finished` 信号中连接 `deleteLater`，C++ 对象被销毁后 Python 引用仍指向已死 wrapper，心跳定时器调用 `isRunning()` 会触发 `RuntimeError`。修复方式（仅 `main_window.py` 已应用）：新增 `_on_deep_scan_done()` 槽函数，在 `deleteLater` 后将 `self._deep_scan_worker = None` 并从 `WorkerManager` 注销；所有 `isRunning()` 调用处加 `try/except RuntimeError` 防护。注意 `left_sidebar.py` 中仍使用旧的 `finished.connect(worker.deleteLater)` 直接模式（该处不调用 `isRunning()`，暂未触发崩溃）；若后续在 `left_sidebar.py` 中加入 `isRunning()` 检查，需同步应用上述修复模式
21. **`FileListView.set_entries()` 会清空 Qt 选中状态**——`beginResetModel()` 是 Qt 框架行为，SelectionModel 会立即清除所有选中索引。Watcher 变更、心跳定时器、手动刷新、Worker 完成均会触发 `set_entries()`。修复方式：在 `FileListView.set_entries()` 中先调用 `selected_paths()` 保存当前选中路径，模型重置后根据路径在新 `_row_of` 中定位行号并通过 `selectionModel().select()` 恢复
22. **`qc_gui/main_window.py` 必须导入 `QTableWidgetItem`**——多版本对比的一致性 Tab 使用该组件构建参数对比表格，漏导会导致点击结果查看一致性时 `NameError` 崩溃
23. **`WorkerManager.stop_all()` 中 `isRunning()` 需 RuntimeError 防护**——Worker 的 C++ 对象被 `deleteLater` 销毁后，Python 引用仍存活，调用 `isRunning()` 触发 `RuntimeError: libshiboken: Internal C++ object already deleted`。修复：`stop_all` 中用 `try/except RuntimeError` 包裹 `isRunning()` 调用，异常时视为 `alive=False`

---

## 16. ADR 记录摘要

- **ADR-001**：采用模块化桌面单体
- **ADR-002**：以服务器项目路径作为当前项目锚点
- **ADR-003**：使用 SQLite WAL 做服务器索引（QC 缓存已移除，每次实时检测）
- **ADR-004**：QC 视觉检测共享一次视频解码
- **ADR-005**：配置 schema 版本化迁移（`CURRENT_SCHEMA_VERSION` + `MIGRATIONS` 链）
- **ADR-006**：QC 检测器插件化注册表（`BaseDetector` + `DetectorRegistry` + adapters）
- **ADR-007**：实时文件监控（`ReadDirectoryChangesW` + daemon 线程 + queue + 防抖 + 增量索引刷新 + 断连补偿 + 同步面板刷新）
- **ADR-008**：QC 检测管线并行调度（FFprobe ∥ FrameScanner、静音 ∥ 视觉检测器、scanner 自算 sample_interval）

---

## 17. 建议阅读顺序

如果你是新接手维护者，推荐顺序：

1. `README.md`
2. `dev/DevHandbook.md`
3. `MediaNexus/constants.py`
4. `MediaNexus/config_manager.py` — 注意 schema 迁移链（ADR-005）
5. `MediaNexus/models.py` — Project 类型化模型
6. `MediaNexus/worker_manager.py` — Worker 统一管理器
7. `MediaNexus/ui/main_window.py`
8. `MediaNexus/watcher.py` — 实时文件监控（ADR-007）
9. `MediaNexus/workers.py`
10. `core/engine.py` — 注意注册表驱动检测（ADR-006）
11. `core/base_detector.py` + `core/adapters.py` — 检测器插件架构
12. `core/frame_scanner.py`
13. `utils/ffmpeg_manager.py`
14. `tests/test_smoke.py` + `tests/test_detectors.py`
