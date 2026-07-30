# ProjectSync Studio -- 全面代码审查报告

**审查日期**: 2026-07-16
**审查范围**: 全部 18 个 Python 源文件
**审查人**: CodeBuddy Code (自动化审查)

---

## 目录

1. [CRITICAL Bugs](#1-critical-bugs)
2. [IMPORTANT Issues](#2-important-issues)
3. [NICE-TO-HAVE Improvements](#3-nice-to-have)

---

## 1. CRITICAL BUGS

### C1: _about() 方法中缺少 QLabel 导入 -- NameError 崩溃

**文件**: D:\Project\ProjectSync-Studio\ProjectSync_Studio\ui\main_window.py
**行号**: 337-365

**问题**: _about() 方法中使用了 QLabel() 但从未导入。模块顶部导入列表（第 17-31 行）不包含 QLabel；方法内联导入（第 337 行）仅导入 QDialog, QVBoxLayout, QDialogButtonBox。

**触发路径**: 菜单栏 帮助 > 关于 -- 100% 可复现崩溃。

`python
# 第 337 行 -- 缺失 QLabel
from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

# 第 343 行 -- 立即崩溃: NameError: name 'QLabel' is not defined
logo_lbl = QLabel()

# 第 353 行 -- 同样崩溃
text = QLabel(...)
`

**严重程度**: CRITICAL -- 点击菜单项即崩溃。

---

### C2: ListWorker 无法被 quit() 中止 -- 旧数据污染与信号干扰

**文件**: middle_panel.py 第 151-158 行, right_panel.py 第 245-252 行

**问题**: _start_list() / _start_worker() 中调用 self._worker.quit()，但 QThread.quit() 仅作用于有事件循环的线程。ListWorker.run() 是同步方法无事件循环，quit() 是空操作。

**后果**:
1. 用户快速切换目录时，可能同时有 2+ 个 ListWorker 运行
2. 旧 worker 完成后发出 loaded 信号，覆盖新结果
3. 信号连接不断累积（从未 disconnect 旧的）

**严重程度**: CRITICAL -- UI 崩溃或显示错误内容。

---

### C3: CopyWorker/MoveWorker/MatchWorker 不支持中断 -- 关闭时线程泄漏

**文件**: workers.py 第 25-46, 148-174, 180-208 行; main_window.py 第 407-426 行

**问题**: closeEvent 调用 requestInterruption() 但 CopyWorker/MoveWorker/MatchWorker.run() 中均未检查 isInterruptionRequested()。主线程阻塞 2 秒后放弃线程。

**后果**: "QThread: Destroyed while thread is still running" 错误; 部分写入文件; 已释放单例的访问崩溃。

**严重程度**: CRITICAL。

---

### C4: ConfigManager.set_confirmed_nas() 中的竞态条件 -- 无锁访问

**文件**: config_manager.py 第 189-205 行

**问题**: set_confirmed_nas() 调用 get_project() 不加锁，然后直接修改 self._data["projects"]。save() 才加锁，但为时已晚。

`python
def set_confirmed_nas(self, local_name: str, nas_path: str) -> None:
    proj = self.get_project(local_name)        # 无锁读取
    if proj is None:
        self.projects.append(proj)              # 无锁写入  <-- 竞态条件
    proj["confirmed_nas_path"] = nas_path       # 无锁写入  <-- 竞态条件
    self.save()                                 # 保存才加锁
`

MatchWorker（后台线程）和 UI（主线程）并发调用时，list 可能崩溃。

**严重程度**: CRITICAL。

---

### C5: middle_panel 中 _on_loaded 缺少陈旧结果保护

**文件**: middle_panel.py 第 160-163 行, right_panel.py 第 254-259 行

**问题**: right_panel.py 有陈旧结果检查（path != self._current_root 时丢弃），但 middle_panel.py 缺失此保护。

`python
# right_panel.py -- 有保护
def _on_loaded(self, path: str, entries: list):
    if path != self._current_root: return  # 丢弃陈旧结果

# middle_panel.py -- 无保护
def _on_loaded(self, path: str, entries: list):
    self.view.set_entries(entries)  # 可能显示旧目录内容
`

**严重程度**: CRITICAL -- 中面板显示错误目录内容。

---

## 2. IMPORTANT ISSUES

### I1: SQLite 只读连接未设置 WAL 模式

**文件**: indexer.py 第 229 行

rebuild() 后通过 _ensure_readonly() 打开只读连接（?mode=ro），但未执行 PRAGMA journal_mode=WAL。原始 WAL 连接关闭时可能未刷新的数据，只读连接可能看不到。

### I2: 信号槽连接泄漏

**文件**: main_window.py 第 194-199 行, middle_panel.py 第 155-158 行, right_panel.py 第 248-252 行

创建新 worker 时信号连接累加，旧信号从未断开。每次 _start_list 调用都新增 loaded.connect 和 error.connect，导致 _on_loaded 被调用 N 次。

### I3: ConfigManager.projects 返回可变内部列表

**文件**: config_manager.py 第 111-112 行

`python
@property
def projects(self) -> list[dict]:
    return self._data.setdefault("projects", [])
`

调用者获得内部列表直接引用。MatchWorker 修改列表时 LeftSidebar.refresh() 可能正在迭代，导致崩溃或遗漏。

### I4: LeftSidebar._apply_filter() 无锁保存配置

**文件**: left_sidebar.py 第 165-167 行

`python
config_manager.settings["sidebar_status_filter"] = self.filter.currentIndex()
config_manager.save()
`

在 textChanged（每次按键）中直接修改内部字典并保存，不加锁。若另一线程并发 save()，JSON 可能交错损坏。

### I5: _RE_LEADING_EP 正则可能过于激进

**文件**: matcher.py 第 19, 68 行

`python
_RE_LEADING_EP = re.compile(r"^\d+[\.\-_]\d+\s+")
`

去除任何数字-分隔符-数字前缀。可能错误剥离 "1.0 Introduction" 等合法名称。

### I6: score_pair() 包含匹配 >= 88 底线过于宽松

**文件**: matcher.py 第 95-121 行

`python
return (max(base, 88), "contains")
`

"龙王" 在 "龙王归来" 中得分 >= 88，即使实际不相关。假阳性增加用户确认负担。

### I7: 跨面板循环导入

**文件**: middle_panel.py 第 216-233 行, right_panel.py 第 161 行

_check_overwrite 定义在 middle_panel.py 但被 right_panel.py 方法内导入。维护脆弱。

### I8: 文件操作无失败回滚

**文件**: workers.py 第 148-208 行

批量复制/移动失败时目标处于部分完成状态。无成功/失败差异列表。

### I9: project_ready 信号未使用

**文件**: main_window.py 第 241 行

`python
self._match_worker.project_ready.connect(lambda p: None)
`

MatchWorker 逐个发出 project_ready，但被丢弃。匹配期间无增量进度。

---

## 3. NICE-TO-HAVE

### N1: 导入时副作用 -- CONFIG_DIR.mkdir()
**文件**: constants.py 第 19 行 -- 导入时创建目录，权限问题会导致整个应用崩溃。建议延迟。

### N2: 重复的 QListWidget 样式选择器
**文件**: constants.py 第 109 行 -- QListWidget 在 CSS 选择器中出现了两次。

### N3: IconMode + ScrollPerPixel 组合
**文件**: file_list_view.py 第 237-238 行 -- 网格模式建议 ScrollPerItem。

### N4: 方法内导入
**文件**: file_list_view.py -- QInputDialog, QMessageBox, shutil 在方法体内多次导入。

### N5: SpinnerLabel.stop() 未隐藏
**文件**: widgets.py 第 35-37 行 -- stop() 不清除布局空间。

### N6: 无 logging 模块
应用未使用 Python logging，错误仅通过 UI 状态栏或静默 pass。

### N7: settings 无 TypedDict
调用者可访问不存在的键。建议 dataclass 或 TypedDict。

### N8: FileListView.closeEvent 是死代码
**文件**: file_list_view.py 第 618-620 行 -- QSplitter 内控件不会收到 closeEvent。

### N9: 令人困惑的三元表达式
**文件**: right_panel.py 第 218 行 -- confirmed 在分支内始终为假，表达式冗余。

### N10: 无单元测试
项目无任何测试文件。

---

## 总结

| 严重程度 | 数量 | 关键发现 |
|----------|------|----------|
| CRITICAL | 5    | QLabel 未导入崩溃、线程不可中断、竞态条件、陈旧数据污染 |
| IMPORTANT | 9    | SQLite 连接、信号泄漏、线程安全、匹配逻辑、代码组织 |
| NICE-TO-HAVE | 10   | 副作用管理、样式错误、死代码、缺少测试 |

### 首要修复优先级

1. 修复 QLabel 导入 -- 单行修复，防止帮助 > 关于崩溃
2. 为 ListWorker 添加中断标志 -- 防止陈旧结果污染 UI
3. 为 CopyWorker/MoveWorker 添加 isInterruptionRequested() 检查 -- 安全关闭
4. 修复 ConfigManager.set_confirmed_nas() 中的锁 -- 防止配置损坏
5. 为中面板添加陈旧结果检查（如右面板已有） -- 防止显示错误目录

---

*报告结束。*
