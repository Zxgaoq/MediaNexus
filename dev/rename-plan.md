# MediaNexus -> MediaNexus / 影枢 重命名变更清单

> 生成时间：2026-07-28
> 本文档列出所有需要修改的文件、行号及精确的 old -> new 对照。
> **执行前请备份，逐文件核对。**

---

## 命名规则

| 上下文 | 旧名 | 新名 |
|:---|:---|:---|
| 中文 UI 字符串（窗口标题、弹窗、菜单） | MediaNexus | **影枢** |
| 英文品牌 / 注释 / docstring | MediaNexus | **MediaNexus** |
| Python 包名 / import | MediaNexus | **MediaNexus** |
| 日志前缀 (logging.getLogger) | MediaNexus.Xxx | **MediaNexus.Xxx** |
| 配置目录 (%APPDATA%) | MediaNexus | **MediaNexus** |
| 旧配置迁移目录 | MediaNexus | **MediaNexus**（过渡） |
| exe / 安装包 / spec | MediaNexus.exe / MediaNexus-Setup.iss | **MediaNexus.exe / MediaNexus-Setup.iss** |
| 用户手册 | MediaNexus-Manual.html | **MediaNexus-Manual.html** |
| GitHub | Zxgaoq/MediaNexus | **Zxgaoq/MediaNexus** |

---

## 一、文件 / 目录重命名（先做）

| 旧路径 | 新路径 |
|:---|:---|
| `MediaNexus/` | `MediaNexus/` |
| `MediaNexus.spec` | `MediaNexus.spec` |
| `installer/MediaNexus-Setup.iss` | `installer/MediaNexus-Setup.iss` |
| `docs/MediaNexus-Manual.html` | `docs/MediaNexus-Manual.html` |

---

## 二、源码文件（Python）

### 2.1 MediaNexus/constants.py (6)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 常量与默认配置` | `MediaNexus - 常量与默认配置` |
| 13 | `APP_NAME = "影枢"` | `APP_NAME = "影枢"` |
| 21 | `os.path.join(tempfile.gettempdir(), "MediaNexus", "spin-arrows")` | `os.path.join(tempfile.gettempdir(), "MediaNexus", "spin-arrows")` |
| 43 | `# 统一以产品名 "MediaNexus" 为目录名（与安装包品牌一致）。` | `# 统一以产品名 "MediaNexus" 为目录名（与安装包品牌一致）。` |
| 44 | `CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "MediaNexus"` | `CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "MediaNexus"` |
| 46 | `_OLD_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "MediaSync"` | `_OLD_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "MediaSync"` |

---

### 2.2 MediaNexus/main.py (4)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 包入口` | `MediaNexus - 包入口` |
| 8 | `from MediaNexus.ui.main_window import run_app` | `from MediaNexus.ui.main_window import run_app` |
| 13 | `%APPDATA%/MediaNexus/crash.log` | `%APPDATA%/MediaNexus/crash.log` |
| 16 | `from MediaNexus.crash_handler import install as _install_crash` | `from MediaNexus.crash_handler import install as _install_crash` |

---

### 2.3 MediaNexus/crash_handler.py (4)

| 行 | old | new |
|:---|:---|:---|
| 12 | `%APPDATA%/MediaNexus/crash.log` | `%APPDATA%/MediaNexus/crash.log` |
| 30 | `base = Path(os.environ.get("APPDATA", Path.home())) / "MediaNexus"` | `base = Path(os.environ.get("APPDATA", Path.home())) / "MediaNexus"` |
| 99 | `_show_box("影枢 发生错误", text)` | `_show_box("影枢 发生错误", text)` |
| 136 | `_show_box("影枢 致命错误 (Qt)", text)` | `_show_box("影枢 致命错误 (Qt)", text)` |

---

### 2.4 MediaNexus/__init__.py (2)

| 行 | old | new |
|:---|:---|:---|
| 2 | `"""MediaNexus - 包初始化（本地项目 <-> NAS 素材同步 + 视频质检一体化）"""` | `"""MediaNexus - 包初始化（本地项目 <-> NAS 素材同步 + 视频质检一体化）"""` |
| 5 | `__app_name__ = "MediaNexus"` | `__app_name__ = "MediaNexus"` |

---

### 2.5 MediaNexus/indexer.py (2)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - NAS 索引器（异步 + SQLite）` | `MediaNexus - NAS 索引器（异步 + SQLite）` |
| 30 | `logger = logging.getLogger("MediaNexus.Indexer")` | `logger = logging.getLogger("MediaNexus.Indexer")` |

---

### 2.6 MediaNexus/watcher.py (2)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - NAS 实时文件监控` | `MediaNexus - NAS 实时文件监控` |
| 28 | `logger = logging.getLogger("MediaNexus.Watcher")` | `logger = logging.getLogger("MediaNexus.Watcher")` |

---

### 2.7 MediaNexus/worker_manager.py (2)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - Worker 统一管理器` | `MediaNexus - Worker 统一管理器` |
| 30 | `logger = logging.getLogger("MediaNexus.WorkerManager")` | `logger = logging.getLogger("MediaNexus.WorkerManager")` |

---

### 2.8 MediaNexus/qc_bridge.py (2)

| 行 | old | new |
|:---|:---|:---|
| 5 | `负责从 MediaNexus 打开 QC 检测窗口 / 多版本对比窗口` | `负责从 MediaNexus 打开 QC 检测窗口 / 多版本对比窗口` |
| 81 | `win.setWindowTitle("影枢 QC")` | `win.setWindowTitle("影枢 QC")` |

---

### 2.9 MediaNexus/config_manager.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 配置管理模块` | `MediaNexus - 配置管理模块` |

---

### 2.10 MediaNexus/matcher.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 智能匹配引擎（核心）` | `MediaNexus - 智能匹配引擎（核心）` |

---

### 2.11 MediaNexus/models.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 数据模型` | `MediaNexus - 数据模型` |

---

### 2.12 MediaNexus/workers.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 后台线程 Workers` | `MediaNexus - 后台线程 Workers` |

---

### 2.13 MediaNexus/utils.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 通用工具函数` | `MediaNexus - 通用工具函数` |

---

### 2.14 MediaNexus/ui/__init__.py (1)

| 行 | old | new |
|:---|:---|:---|
| 2 | `"""MediaNexus - UI 子包"""` | `"""MediaNexus - UI 子包"""` |

---

### 2.15 MediaNexus/ui/add_project_dialog.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 添加项目对话框` | `MediaNexus - 添加项目对话框` |

---

### 2.16 MediaNexus/ui/file_list_view.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 文件列表视图（中栏 / 右栏共用）v2 重写版` | `MediaNexus - 文件列表视图（中栏 / 右栏共用）v2 重写版` |

---

### 2.17 MediaNexus/ui/left_sidebar.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 左侧边栏：项目导航` | `MediaNexus - 左侧边栏：项目导航` |

---

### 2.18 MediaNexus/ui/main_window.py (4)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 主窗口（三栏式布局 + 整体调度）` | `MediaNexus - 主窗口（三栏式布局 + 整体调度）` |
| 458 | `logging.getLogger("MediaNexus.Watcher").warning(...)` | `logging.getLogger("MediaNexus.Watcher").warning(...)` |
| 481 | `logging.getLogger("MediaNexus.Watcher").warning(...)` | `logging.getLogger("MediaNexus.Watcher").warning(...)` |
| 840 | `f"影枢 已更新到 v{APP_VERSION}"` | `f"影枢 已更新到 v{APP_VERSION}"` |

---

### 2.19 MediaNexus/ui/middle_panel.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 中间栏：本地项目内容` | `MediaNexus - 中间栏：本地项目内容` |

---

### 2.20 MediaNexus/ui/preset_panel.py (1)

| 行 | old | new |
|:---|:---|:---|
| 5 | `改为读写 MediaNexus config_manager 的 qc_presets / qc_active_preset。` | `改为读写 MediaNexus config_manager 的 qc_presets / qc_active_preset。` |

---

### 2.21 MediaNexus/ui/right_panel.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 右侧栏：服务器匹配内容` | `MediaNexus - 右侧栏：服务器匹配内容` |

---

### 2.22 MediaNexus/ui/settings_dialog.py (2)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 设置对话框（多选项卡版本）` | `MediaNexus - 设置对话框（多选项卡版本）` |
| 50 | `self.setWindowTitle("设置 - 影枢")` | `self.setWindowTitle("设置 - 影枢")` |

---

### 2.23 MediaNexus/ui/widgets.py (1)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - 通用小组件` | `MediaNexus - 通用小组件` |

---

### 2.24 run.py (2)

| 行 | old | new |
|:---|:---|:---|
| 15 | `from MediaNexus.crash_handler import install as _install_crash_handler` | `from MediaNexus.crash_handler import install as _install_crash_handler` |
| 40 | `from MediaNexus.main import main` | `from MediaNexus.main import main` |

---

### 2.25 utils/config.py (6)

| 行 | old | new |
|:---|:---|:---|
| 16 | `# 主程序（MediaNexus / MediaNexus）配置单例的懒加载` | `# 主程序（MediaNexus）配置单例的懒加载` |
| 18 | `# 当本模块在 MediaNexus 主程序进程内被拉起时` | `# 当本模块在 MediaNexus 主程序进程内被拉起时` |
| 33 | `from MediaNexus.config_manager import config_manager as cm` | `from MediaNexus.config_manager import config_manager as cm` |
| 178 | `若运行在 MediaNexus（MediaNexus）主程序进程内，复用主程序的` | `若运行在 MediaNexus 主程序进程内，复用主程序的` |
| 196 | `优先从主程序（MediaNexus）的 %APPDATA% 配置读取 qc_presets /` | `优先从主程序（MediaNexus）的 %APPDATA% 配置读取 qc_presets /` |
| 310 | `若运行在 MediaNexus 主程序内，直接写入主程序配置单例的 qc_presets /` | `若运行在 MediaNexus 主程序内，直接写入主程序配置单例的 qc_presets /` |

---

### 2.26 utils/docs_viewer.py (3)

| 行 | old | new |
|:---|:---|:---|
| 5 | `优先使用 Qt WebEngine（QWebEngineView）以「网页」方式渲染 docs/MediaNexus-Manual.html；` | `...渲染 docs/MediaNexus-Manual.html；` |
| 16 | `MANUAL_FILENAME = "MediaNexus-Manual.html"` | `MANUAL_FILENAME = "MediaNexus-Manual.html"` |
| 44 | `dlg.setWindowTitle("影枢 用户手册")` | `dlg.setWindowTitle("影枢 用户手册")` |

---

### 2.27 utils/ffmpeg_manager.py (7)

| 行 | old | new |
|:---|:---|:---|
| 8 | `%APPDATA%/MediaNexus/ffmpeg/bin（兜底）` | `%APPDATA%/MediaNexus/ffmpeg/bin（兜底）` |
| 52 | `"""跨平台的应用数据目录（与 CONFIG_DIR=%APPDATA%/MediaNexus 对齐）。"""` | `"""跨平台的应用数据目录（与 CONFIG_DIR=%APPDATA%/MediaNexus 对齐）。"""` |
| 56 | `d = os.path.join(base, "MediaNexus")` | `d = os.path.join(base, "MediaNexus")` |
| 85 | `from MediaNexus.config_manager import config_manager` | `from MediaNexus.config_manager import config_manager` |
| 93 | `from MediaNexus.config_manager import config_manager` | `from MediaNexus.config_manager import config_manager` |
| 193 | `from MediaNexus.config_manager import config_manager` | `from MediaNexus.config_manager import config_manager` |
| 221 | `tmp_dir = tempfile.mkdtemp(prefix="medianexus_ff_")` | `tmp_dir = tempfile.mkdtemp(prefix="medianexus_ff_")` |

---

### 2.28 utils/onboarding.py (3)

| 行 | old | new |
|:---|:---|:---|
| 27 | `from MediaNexus.config_manager import config_manager` | `from MediaNexus.config_manager import config_manager` |
| 28 | `from MediaNexus.constants import APP_NAME` | `from MediaNexus.constants import APP_NAME` |
| 29 | `from MediaNexus.utils import resource_path` | `from MediaNexus.utils import resource_path` |

---

### 2.29 utils/storage_manager.py (7)

| 行 | old | new |
|:---|:---|:---|
| 284 | `# 1. QC 检测结果缓存（%APPDATA%/MediaNexus/qc_cache.db）` | `# 1. QC 检测结果缓存（%APPDATA%/MediaNexus/qc_cache.db）` |
| 402 | `from MediaNexus.constants import CONFIG_DIR` | `from MediaNexus.constants import CONFIG_DIR` |
| 405 | `os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "qc_cache.db")` | `os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "qc_cache.db")` |
| 409 | `from MediaNexus.constants import CONFIG_DIR` | `from MediaNexus.constants import CONFIG_DIR` |
| 412 | `os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "ffmpeg")` | `os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "ffmpeg")` |
| 416 | `from MediaNexus.constants import CONFIG_DIR` | `from MediaNexus.constants import CONFIG_DIR` |
| 419 | `os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "crash.log")` | `os.path.join(os.environ.get("APPDATA", ""), "MediaNexus", "crash.log")` |

---

### 2.30 qc_gui/main_window.py (4)

| 行 | old | new |
|:---|:---|:---|
| 205 | `self.setWindowTitle("影枢 QC")` | `self.setWindowTitle("影枢 QC")` |
| 1208 | `self, "关于 影枢 QC",` | `self, "关于 影枢 QC",` |
| 1209 | `"<h2>影枢 QC</h2>"` | `"<h2>影枢 QC</h2>"` |
| 1210 | `"<p>视频批量质量检测工具（MediaNexus 一体化套件之质检子系统）</p>"` | `"<p>视频批量质量检测工具（影枢一体化套件之质检子系统）</p>"` |

---

### 2.31 qc_gui/widgets/toolbar.py (1)

| 行 | old | new |
|:---|:---|:---|
| 20 | `title_label = QLabel("影枢 QC")` | `title_label = QLabel("影枢 QC")` |

---

### 2.32 tests/test_smoke.py (6)

| 行 | old | new |
|:---|:---|:---|
| 2 | `MediaNexus 防回归冒烟测试` | `MediaNexus 防回归冒烟测试` |
| 24 | `from MediaNexus import constants` | `from MediaNexus import constants` |
| 25 | `from MediaNexus import config_manager` | `from MediaNexus import config_manager` |
| 26 | `from MediaNexus import indexer` | `from MediaNexus import indexer` |
| 27 | `from MediaNexus import matcher` | `from MediaNexus import matcher` |
| 275 | `from MediaNexus.watcher import NASWatchThread` | `from MediaNexus.watcher import NASWatchThread` |

---

### 2.33 tests/test_detectors.py (1)

| 行 | old | new |
|:---|:---|:---|
| 13 | `from MediaNexus.models import Project` | `from MediaNexus.models import Project` |

---

### 2.34 scripts/fetch_ffmpeg.py (2)

| 行 | old | new |
|:---|:---|:---|
| 43 | `req = urllib.request.Request(url, headers={"User-Agent": "MediaNexus-Build/1.0"})` | `req = urllib.request.Request(url, headers={"User-Agent": "MediaNexus-Build/1.0"})` |
| 123 | `tmp = tempfile.mkdtemp(prefix="medianexus_fffetch_")` | `tmp = tempfile.mkdtemp(prefix="medianexus_fffetch_")` |

---

## 三、构建 / 打包文件

### 3.1 MediaNexus.spec (8)

| 行 | old | new |
|:---|:---|:---|
| 3 | `MediaNexus - PyInstaller 打包配置（onedir 模式）` | `MediaNexus - PyInstaller 打包配置（onedir 模式）` |
| 4 | `运行：python -m PyInstaller MediaNexus.spec --clean --noconfirm` | `运行：python -m PyInstaller MediaNexus.spec --clean --noconfirm` |
| 5 | `产出：dist/MediaNexus/ 目录（含 MediaNexus.exe + 全部 DLL / assets / docs）` | `产出：dist/MediaNexus/ 目录（含 MediaNexus.exe + 全部 DLL / assets / docs）` |
| 6 | `配合 installer/MediaNexus-Setup.iss 一键打包为 Windows 安装程序` | `配合 installer/MediaNexus-Setup.iss 一键打包为 Windows 安装程序` |
| 52 | `['MediaNexus/main.py'],` | `['MediaNexus/main.py'],` |
| 81 | `# onedir 模式：exe 与所有 DLL 放在同一目录（dist/MediaNexus/）。` | `# onedir 模式：exe 与所有 DLL 放在同一目录（dist/MediaNexus/）。` |
| 89 | `name='MediaNexus',` | `name='MediaNexus',` |
| 113 | `name='MediaNexus',` | `name='MediaNexus',` |

---

### 3.2 build.bat (5)

| 行 | old | new |
|:---|:---|:---|
| 4 | `REM  MediaNexus packaging script (onedir folder, no install wizard)` | `REM  MediaNexus packaging script (onedir folder, no install wizard)` |
| 7 | `REM  Output: dist\MediaNexus\  (folder with MediaNexus.exe + DLLs + assets/docs)` | `REM  Output: dist\MediaNexus\  (folder with MediaNexus.exe + DLLs + assets/docs)` |
| 13 | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` |
| 16 | `echo [OK] Generated folder: dist\MediaNexus\` | `echo [OK] Generated folder: dist\MediaNexus\` |
| 17 | `echo      Run dist\MediaNexus\MediaNexus.exe to launch.` | `echo      Run dist\MediaNexus\MediaNexus.exe to launch.` |

---

### 3.3 installer/MediaNexus-Setup.iss (11)

| 行 | old | new |
|:---|:---|:---|
| 2 | `; MediaNexus 安装程序脚本（Inno Setup 6）` | `; MediaNexus 安装程序脚本（Inno Setup 6）` |
| 5 | `; 用法（在项目根目录下，已先执行 PyInstaller 打包出 dist\MediaNexus.exe）：` | `; 用法（在项目根目录下，已先执行 PyInstaller 打包出 dist\MediaNexus.exe）：` |
| 5 | `installer\MediaNexus-Setup.iss` (同行末尾) | `installer\MediaNexus-Setup.iss` |
| 7 | `; 产出：dist\installer\MediaNexus-Setup.exe` | `; 产出：dist\installer\MediaNexus-Setup.exe` |
| 12 | `;   - 用户可选择安装位置（默认 C:\Program Files\MediaNexus）` | `;   - 用户可选择安装位置（默认 C:\Program Files\MediaNexus）` |
| 14 | `;   - 卸载时不删除用户配置（%APPDATA%\MediaNexus）` | `;   - 卸载时不删除用户配置（%APPDATA%\MediaNexus）` |
| 17 | `#define MyAppName      "MediaNexus"` | `#define MyAppName      "MediaNexus"` |
| 20 | `#define MyAppExeName   "MediaNexus.exe"` | `#define MyAppExeName   "MediaNexus.exe"` |
| 39 | `OutputBaseFilename=MediaNexus-Setup` | `OutputBaseFilename=MediaNexus-Setup` |
| 69 | `Source: "{#SourceRoot}\dist\MediaNexus\*";` | `Source: "{#SourceRoot}\dist\MediaNexus\*";` |
| 74 | `Name: "{group}\用户手册"; Filename: "{app}\_internal\docs\MediaNexus-Manual.html"` | `...MediaNexus-Manual.html"` |

---

### 3.4 installer/build-installer.bat (9)

| 行 | old | new |
|:---|:---|:---|
| 4 | `REM  MediaNexus installer build script` | `REM  MediaNexus installer build script` |
| 7 | `REM  Output: dist\installer\MediaNexus-Setup.exe` | `REM  Output: dist\installer\MediaNexus-Setup.exe` |
| 21 | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` |
| 27 | `if not exist "dist\MediaNexus\MediaNexus.exe" (` | `if not exist "dist\MediaNexus\MediaNexus.exe" (` |
| 28 | `echo [FAIL] dist\MediaNexus\MediaNexus.exe not generated. Check MediaNexus.spec` | `echo [FAIL] dist\MediaNexus\MediaNexus.exe not generated. Check MediaNexus.spec` |
| 32 | `echo        Generated dist\MediaNexus\MediaNexus.exe` | `echo        Generated dist\MediaNexus\MediaNexus.exe` |
| 35 | `"%INNO_DIR%\ISCC.exe" "installer\MediaNexus-Setup.iss"` | `"%INNO_DIR%\ISCC.exe" "installer\MediaNexus-Setup.iss"` |
| 38 | `echo [OK] Installer generated: dist\installer\MediaNexus-Setup.exe` | `echo [OK] Installer generated: dist\installer\MediaNexus-Setup.exe` |
| 42 | `echo [FAIL] Inno Setup compile error. Check installer\MediaNexus-Setup.iss` | `echo [FAIL] Inno Setup compile error. Check installer\MediaNexus-Setup.iss` |

---

## 四、文档

### 4.1 README.md (19)

| 行 | old | new |
|:---|:---|:---|
| 2 | `<img src="assets/logo.png" alt="MediaNexus" width="96" />` | `alt="MediaNexus"` |
| 5 | `<h1 align="center">MediaNexus</h1>` | `<h1 align="center">MediaNexus</h1>` |
| 17 | `Zxgaoq/MediaNexus` (badge URL) | `Zxgaoq/MediaNexus` |
| 25 | `git clone https://github.com/Zxgaoq/MediaNexus.git` | `...Zxgaoq/MediaNexus.git` |
| 26 | `cd MediaNexus` | `cd MediaNexus` |
| 44 | `### ProjectSync -- 素材同步` | `### MediaNexus -- 素材同步` |
| 69 | `MediaNexus/` | `MediaNexus/` |
| 71 | `├── MediaNexus/         # 主程序包（PyInstaller 入口）` | `├── MediaNexus/                 # 主程序包（PyInstaller 入口）` |
| 89 | `├── MediaNexus.spec     # PyInstaller 打包配置` | `├── MediaNexus.spec             # PyInstaller 打包配置` |
| 96 | `MediaNexus   ->  主程序、项目管理、NAS 索引、UI` | `MediaNexus            ->  主程序、项目管理、NAS 索引、UI` |
| 111 | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` |
| 114 | `输出：\`dist/MediaNexus/\`（onedir 分发）` | `输出：\`dist/MediaNexus/\`（onedir 分发）` |
| 119 | `"...\ISCC.exe" installer\MediaNexus-Setup.iss` | `...installer\MediaNexus-Setup.iss` |
| 122 | `输出：\`dist/installer/MediaNexus-Setup.exe\`` | `输出：\`dist/installer/MediaNexus-Setup.exe\`` |
| 124 | `> 安装包不会删除 \`%APPDATA%/MediaNexus\` 下的用户配置。` | `...%APPDATA%/MediaNexus...` |
| 141 | `\| 打包 \| 启动 \`dist/MediaNexus/MediaNexus.exe\` \|` | `\| 打包 \| 启动 \`dist/MediaNexus/MediaNexus.exe\` \|` |
| 147 | `运行时配置存放于 \`%APPDATA%/MediaNexus/\`：` | `...%APPDATA%/MediaNexus/...` |
| 154 | `\`%APPDATA%/MediaNexus/ffmpeg/bin\`` | `\`%APPDATA%/MediaNexus/ffmpeg/bin\`` |
| 161 | `- [用户手册](docs/MediaNexus-Manual.html)` | `- [用户手册](docs/MediaNexus-Manual.html)` |

---

### 4.2 dev/DevHandbook.md (34)

| 行 | old | new |
|:---|:---|:---|
| 1 | `# MediaNexus 开发手册` | `# MediaNexus 开发手册` |
| 13 | `\| 产品名 \| **MediaNexus** \|` | `\| 产品名 \| **MediaNexus** \|` |
| 18 | `\| 打包入口 \| \`MediaNexus/main.py\` \|` | `\| 打包入口 \| \`MediaNexus/main.py\` \|` |
| 19 | `\| 主配置路径 \| \`%APPDATA%/MediaNexus/config.json\` \|` | `...%APPDATA%/MediaNexus/config.json...` |
| 20 | `\| 索引数据库 \| \`%APPDATA%/MediaNexus/nas_index.db\` \|` | `...%APPDATA%/MediaNexus/nas_index.db...` |
| 23 | `旧目录 \`%APPDATA%/MediaNexus\` 仅用于自动迁移。当前新代码与新文档都应以 \`%APPDATA%/MediaNexus/\` 为准。` | `旧目录 \`%APPDATA%/MediaNexus\` ...应以 \`%APPDATA%/MediaNexus/\` 为准。` |
| 96 | `\| \`MediaNexus\` \| 主程序、项目列表...` | `\| \`MediaNexus\` \| 主程序、项目列表...` |
| 106 | `- \`MediaNexus/config_manager.py\` 是主配置唯一权威来源` | `- \`MediaNexus/config_manager.py\` 是主配置唯一权威来源` |
| 118 | `python -m MediaNexus.main` | `python -m MediaNexus.main` |
| 127 | `-> import MediaNexus.main.main` | `-> import MediaNexus.main.main` |
| 131 | `MediaNexus.main.main()` | `MediaNexus.main.main()` |
| 133 | `-> 调用 MediaNexus.ui.main_window.run_app()` | `-> 调用 MediaNexus.ui.main_window.run_app()` |
| 140 | `- PyInstaller 直接使用 \`MediaNexus/main.py\`` | `- PyInstaller 直接使用 \`MediaNexus/main.py\`` |
| 150 | `├── MediaNexus/            主程序包` | `├── MediaNexus/                    主程序包` |
| 176 | `├── docs/MediaNexus-Manual.html     用户手册` | `├── docs/MediaNexus-Manual.html    用户手册` |
| 180 | `├── MediaNexus.spec        PyInstaller onedir 配置` | `├── MediaNexus.spec                PyInstaller onedir 配置` |
| 298 | `主配置路径：\`%APPDATA%/MediaNexus/config.json\`` | `...%APPDATA%/MediaNexus/config.json...` |
| 336 | `- \`APP_NAME = "影枢"\`` | `- \`APP_NAME = "影枢"\`` |
| 338 | `- \`CONFIG_DIR = Path(APPDATA) / "MediaNexus"\`` | `- \`CONFIG_DIR = Path(APPDATA) / "MediaNexus"\`` |
| 503 | `4. \`%APPDATA%/MediaNexus/ffmpeg/bin\`` | `4. \`%APPDATA%/MediaNexus/ffmpeg/bin\`` |
| 526 | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` | `python -m PyInstaller MediaNexus.spec --clean --noconfirm` |
| 529 | `输出目录：\`dist/MediaNexus/\`` | `输出目录：\`dist/MediaNexus/\`` |
| 534 | `"...\ISCC.exe" installer\MediaNexus-Setup.iss` | `...installer\MediaNexus-Setup.iss` |
| 537 | `安装器输出：\`dist/installer/MediaNexus-Setup.exe\`` | `...MediaNexus-Setup.exe...` |
| 542 | `- 用户配置与缓存保留在 \`%APPDATA%/MediaNexus\`` | `...%APPDATA%/MediaNexus...` |
| 587 | `\| 打包配置 \| 启动 \`dist/MediaNexus/MediaNexus.exe\` \|` | `...dist/MediaNexus/MediaNexus.exe...` |
| 680 | `3. \`MediaNexus/constants.py\`` | `3. \`MediaNexus/constants.py\`` |
| 681 | `4. \`MediaNexus/config_manager.py\`` | `4. \`MediaNexus/config_manager.py\`` |
| 682 | `5. \`MediaNexus/models.py\`` | `5. \`MediaNexus/models.py\`` |
| 683 | `6. \`MediaNexus/worker_manager.py\`` | `6. \`MediaNexus/worker_manager.py\`` |
| 684 | `7. \`MediaNexus/ui/main_window.py\`` | `7. \`MediaNexus/ui/main_window.py\`` |
| 685 | `8. \`MediaNexus/watcher.py\`` | `8. \`MediaNexus/watcher.py\`` |
| 686 | `9. \`MediaNexus/workers.py\`` | `9. \`MediaNexus/workers.py\`` |

---

### 4.3 docs/MediaNexus-Manual.html (10)

| 行 | old | new |
|:---|:---|:---|
| 6 | `<title>影枢 用户手册</title>` | `<title>影枢 用户手册</title>` |
| 53 | `<h1>影枢 用户手册</h1>` | `<h1>影枢 用户手册</h1>` |
| 57 | `MediaNexus 把两件麻烦事合在一起` | `影枢 把两件麻烦事合在一起` |
| 63 | `<code>%APPDATA%\MediaNexus\config.json</code>` | `<code>%APPDATA%\MediaNexus\config.json</code>` |
| 78 | `<th>传统做法</th><th>MediaNexus</th>` | `<th>传统做法</th><th>影枢</th>` |
| 95 | `<a href="#qc">打开 影枢 QC 做视频质检</a>` | `打开 影枢 QC 做视频质检` |
| 141 | `<h2 id="qc">视频质检（影枢 QC）</h2>` | `视频质检（影枢 QC）` |
| 142 | `标题为 <b>「影枢 QC」</b>` (两处: 标题 + 正文) | `标题为 <b>「影枢 QC」</b>` |
| 176 | `<code>%APPDATA%\MediaNexus\config.json</code>` | `<code>%APPDATA%\MediaNexus\config.json</code>` |
| 179 | `<footer>MediaNexus · 影视全行业素材同步与质检工具...` | `<footer>影枢 · 影视全行业素材同步与质检工具...` |

---

### 4.4 requirements.txt (1)

| 行 | old | new |
|:---|:---|:---|
| 1 | `# MediaNexus 运行依赖` | `# MediaNexus 运行依赖` |

---

## 五、变更统计

| 类别 | 文件数 | 变更行数 |
|:---|---:|---:|
| Python 源码（MediaNexus/） | 23 | 44 |
| Python 源码（run.py） | 1 | 2 |
| Python 源码（utils/） | 5 | 22 |
| Python 源码（qc_gui/） | 2 | 5 |
| Python 源码（tests/） | 2 | 7 |
| Python 源码（scripts/） | 1 | 2 |
| 构建 / 打包 | 4 | 33 |
| 文档 | 4 | 64 |
| 文件 / 目录重命名 | 4 | - |
| **合计** | **46** | **~179** |

---

## 六、执行顺序建议

1. **重命名目录与文件**（第一部分表格中的 4 项）
2. **修改 constants.py** -- APP_NAME / CONFIG_DIR / _OLD_CONFIG_DIR 是其他模块的依赖根
3. **修改 __init__.py / main.py / crash_handler.py** -- 包入口
4. **修改其余 MediaNexus/*.py** -- docstring + logger + import
5. **修改 run.py** -- 开发入口 import
6. **修改 utils/*.py** -- 配置代理、FFmpeg、存储、文档查看器、引导
7. **修改 qc_gui/ + tests/ + scripts/** -- QC 子系统与测试
8. **修改 .spec + build.bat + installer/** -- 打包链路
9. **修改 README.md + DevHandbook.md + Manual.html + requirements.txt** -- 文档
10. **全量验证**：`python run.py` 启动 + `python -m pytest tests/ -q` + 打包测试

---

## 七、注意事项

- `_OLD_CONFIG_DIR` 从 `MediaNexus` 改为 `MediaNexus`（过渡），确保已升级到 MediaNexus 的用户在再次升级后配置仍能自动迁移到 `MediaNexus`。
- `APP_NAME` 改为 `"影枢"` 后，所有引用该常量的窗口标题、弹窗、关于对话框自动生效（main_window / onboarding / settings_dialog）。
- `logging.getLogger("MediaNexus.Xxx")` 全部改为 `"MediaNexus.Xxx"`，确保日志前缀统一。
- 用户手册 HTML 中的 `%APPDATA%\MediaNexus` 是历史遗留路径，应统一改为 `%APPDATA%\MediaNexus`（当前实际路径）。
- GitHub badge URL、clone URL 均需同步更新。
- 打包产物目录名从 `dist/MediaNexus/` 变为 `dist/MediaNexus/`，spec 中的 `name` 字段控制此行为。
- Inno Setup 的 `MyAppId` GUID 保持不变，确保覆盖安装兼容。
