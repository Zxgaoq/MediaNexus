# MediaSync — 异常处理清单

本清单列出软件在真实 Windows / NAS 环境下可能遇到的异常场景，以及对应的处理方案与代码位置，便于排查与二次开发。

| # | 场景 | 触发原因 | 处理方式 | 代码位置 |
| --- | --- | --- | --- | --- |
| 1 | **NAS 断连 / 网络抖动** | 网线松动、NAS 重启、VPN 掉线 | 右栏访问失败自动**重试 3 次**（间隔 1.5s）；仍失败显示「重试」按钮，用户可手动重连后再试 | `ui/right_panel.py` `_on_error` / `_retry_now`；常量见 `constants.NAS_RETRY_*` |
| 2 | **权限不足（PermissionError）** | 无读取权限的目录/文件 | 单目录/文件**跳过并计入错误数**，不影响整体索引；UI 不弹窗打断 | `indexer.py` `_scan_dir` 内 try/except；`utils.list_dir_safe` 跳过无权限项 |
| 3 | **路径无效 / 不存在** | 用户填错、盘符未挂载 | 设置保存前校验本地根目录必填；索引/列举对空路径做存在性判断并提示，不崩溃 | `ui/settings_dialog.py` `_accept`；`workers.ListWorker` error 信号 |
| 4 | **UNC 路径不可达** | 服务器名解析失败、未登录凭据 | 列举失败走异常分支，UI 提示“无法访问 NAS：<错误>”，并提供重试 | `workers.ListWorker` → `right_panel._on_error` |
| 5 | **中文路径乱码** | 非 UTF-8 编解码 | 全程 `utf-8`：配置 JSON `ensure_ascii=False`；路径用 `os.path`/`Path` 原生处理；开启 `AA_EnableHighDpiScaling` 避免 DPI 缩放模糊 | `config_manager.py`；`ui/main_window.py` `run_app` |
| 6 | **索引过程被中断（用户关闭/暂停）** | 用户点暂停或强制退出 | 索引在**后台线程**运行，支持 `pause_event` 暂停/继续、`stop_event` 中止；退出时触发 `closeEvent` 置 stop 并 `quit()` | `workers.IndexWorker`；`main_window.closeEvent`；`indexer.rebuild` |
| 7 | **配置文件损坏** | 异常关机导致 JSON 截断 | 加载时 `json.JSONDecodeError` 捕获 → **回退默认配置且不覆盖原文件**；保存采用**临时文件 + 原子替换**，避免写一半损坏 | `config_manager.load` / `save` |
| 8 | **单文件夹万级文件** | NAS 成片/素材海量 | `QAbstractTableModel + fetchMore` **虚拟滚动 + 懒加载**，仅渲染可见行；后台线程分页读取，UI 不阻塞 | `ui/file_list_view.py` `FileListViewModel` |
| 9 | **拖拽复制失败** | 目标只读、文件名冲突、NAS 又断 | `CopyWorker` 逐文件复制，统计**成功/失败**数量；失败项跳过不中断，完成提示“成功 x，失败 y” | `workers.CopyWorker`；`middle_panel._on_files_dropped` |
| 10 | **高 DPI 下界面模糊** | 4K/缩放 150% | `QApplication` 设置 `AA_EnableHighDpiScaling` + `AA_UseHighDpiPixmaps`，并采用 Fusion 风格 | `ui/main_window.py` `run_app` |
| 11 | **匹配结果不理想（误/漏）** | 阈值不当、忽略词误伤 | 提供**阈值滑杆（0-100）**与**忽略词列表**即时调整；支持「排除此结果」降权重匹配、「确认为此项目」人工锁定 | `ui/settings_dialog.py`；`ui/right_panel.py` |
| 12 | **剪贴板写入失败** | 无 `pywin32` / 被其他程序占用 | 先尝试 `win32clipboard`，失败回退 PowerShell `Set-Clipboard`，再失败静默忽略 | `utils.copy_path_to_clipboard` |
| 13 | **aiofiles 异步目录遍历异常** | 网络目录中途消失 | `scandir` 与迭代分别 try/except，单目录失败计入 errors 并继续，整体索引不中断 | `indexer._scan_dir` |
| 14 | **多线程并发写 SQLite** | 多 worker 同时落库 | 单一连接 + `asyncio.Lock` 串行化写入；采用 WAL 模式提升并发读性能 | `indexer._walk` / `_scan_dir`；`PRAGMA journal_mode=WAL` |

### 设计原则回顾
- **UI 永不阻塞**：所有耗时操作（索引、匹配、列举、复制）均在 `QThread` 子线程；NAS I/O 进一步使用 `asyncio + aiofiles` 异步。
- **用户操作即时持久化**：确认 / 排除 / 设置变更均立即写入 `config.json`（原子替换）。
- **失败隔离**：单个目录 / 文件异常不影响整体任务；错误计数可见，便于判断是否需排查 NAS。
- **可恢复**：索引可暂停/继续；配置损坏可回退；NAS 断连可重试。
