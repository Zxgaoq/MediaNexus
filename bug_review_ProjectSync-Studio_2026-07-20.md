# ProjectSync-Studio Bug 审查报告

审查方式：静态代码阅读 + 小范围运行时验证（`py_compile`、PySide6 枚举验证、Python 作用域验证）
范围：`run.py`、`ProjectSync_Studio/*.py`、`ProjectSync_Studio/ui/*.py`
结论：本轮确认的问题已全部修复，当前剩余风险主要是缺少真实 NAS 环境下的端到端复测。

## 已修复的高优问题

### 1. NAS 索引进度回调的 `UnboundLocalError`
- 位置：`ProjectSync_Studio/indexer.py`
- 修复：将进度计数改为可变字典 `last_report["dirs"]`，避免闭包内部对局部变量的错误重绑定。
- 验证：最小 Python 作用域测试已通过。

### 2. 索引遍历“队列暂空即退出”导致的漏扫
- 位置：`ProjectSync_Studio/indexer.py`
- 修复：去掉 `get_nowait() + active count` 的竞争式退出逻辑，改为 `queue.join()` 等待所有任务完成，并用哨兵值安全回收 worker。
- 预期效果：深层目录不会因为并发时序问题被跳过。

### 3. 侧栏右键菜单的 `AttributeError`
- 位置：`ProjectSync_Studio/ui/left_sidebar.py`
- 修复：将 `Qt.ItemSelectionModel.ClearAndSelect` 改为 `QItemSelectionModel.ClearAndSelect`。
- 验证：已在当前 PySide6 环境确认该枚举可用。

### 4. 删除目录失败被误报为成功
- 位置：`ProjectSync_Studio/ui/file_list_view.py`
- 修复：移除 `shutil.rmtree(..., ignore_errors=True)`，改为显式抛错并汇总到失败列表。
- 预期效果：权限不足、文件占用或 NAS 异常时，界面会正确提示删除失败，而不是静默吞错。

## 本轮补充修复

### 5. 启动失败时重复创建 `QApplication`
- 位置：`run.py`
- 修复：`_show_error()` 先取 `QApplication.instance()`，仅在没有实例时创建临时应用，再弹出错误框。
- 同时修正了错误提示里不存在的 `start.bat` 文案。

### 6. 已确认 NAS 路径失效后仍显示 `matched`
- 位置：`ProjectSync_Studio/workers.py`
- 修复：匹配时会校验 `confirmed_nas_path` 是否仍在已索引 NAS 路径中；失效则清空确认路径，并按候选重新计算状态。

### 7. “重新匹配此项目”误触发全量匹配
- 位置：`ProjectSync_Studio/ui/left_sidebar.py`、`ProjectSync_Studio/ui/main_window.py`、`ProjectSync_Studio/workers.py`
- 修复：侧栏信号改为携带项目名；主窗口按项目名触发定向重匹配；`MatchWorker` 新增 `project_names` 过滤，只处理指定项目。

### 8. README 与当前实现不一致
- 位置：`README.md`、`EXCEPTIONS.md`
- 修复：校正了“系统级复制”“索引自动重试”“QAbstractListModel”等过期描述，确保文档与当前代码一致。

## 后续建议

1. 用真实 NAS 环境做一次端到端回归，重点覆盖索引、确认路径失效、右栏自动重试和单项目重匹配。
2. 如果要降低删除风险，建议后续把永久删除改为回收站语义。

## 依赖补充与测试结果

在 `.venv` 中安装缺失依赖后重新测试，结果如下：

- `diagnose.py`：`PySide6 6.11.1`、`rapidfuzz 3.14.5`、`aiofiles` 均可用；本地根 `E:/项目`，NAS 根 `Z:\AIGC\AIGC项目`、`Z:\AIGC\AIGC解说剧`。
- 无头启动 `MainWindow`（`QT_QPA_PLATFORM=offscreen`）：窗口创建成功，读取到 285 个已索引 NAS 文件夹，左侧 21 个项目，状态栏进入匹配流程。
- 索引重建定向测试：临时 3 层嵌套目录 + 并发 worker，最终索引到 6 个文件夹（含 `A/A1/A2` 深层目录），`errors=0`，进度回调未触发 `UnboundLocalError`。
- 匹配逻辑测试：`normalize_name`、`score_pair`、`match_project`、`decide_status` 行为符合预期。
- `MatchWorker` 定向测试（临时配置，不污染真实配置）：
  - 全量匹配覆盖 Alpha、Beta 两个项目；
  - 单项目重匹配（`project_names=['Beta']`）只处理指定项目；
  - 失效确认路径 `/gone/path` 被清空，状态按候选重新计算；
  - 有效确认路径 `Z:/NAS/Alpha` 保留，状态保持 `matched`。
- 删除逻辑测试：移除 `ignore_errors=True` 后，删除不存在路径会抛 `OSError` 并进入失败列表，不再静默吞错。

结论：代码层面已修复的问题均通过运行时验证；唯一未覆盖的是真实 NAS 网络环境端到端回归，因为本机 NAS 映射盘状态依赖实际网络。