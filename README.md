<p align="center">
  <img src="assets/logo.png" alt="MediaNexus" width="96" />
</p>

<h1 align="center">MediaNexus</h1>

<p align="center">
  <b>素材同步 + 视频质检</b> 一体化桌面工具<br/>
  <sub>面向影视后期素材生产流程</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python" />
  <img src="https://img.shields.io/badge/%E5%B9%B3%E5%8F%B0-Windows%2010%2F11-lightgrey" alt="平台" />
  <img src="https://img.shields.io/badge/%E6%A1%86%E6%9E%B6-PySide6-green" alt="框架" />
  <img src="https://img.shields.io/badge/%E7%89%88%E6%9C%AC-1.1.0-orange" alt="版本" />
  <img src="https://img.shields.io/github/last-commit/Zxgaoq/MediaNexus" alt="最近提交" />
</p>

---

## 快速开始

```bash
git clone https://github.com/Zxgaoq/MediaNexus.git
cd MediaNexus

# 安装依赖
pip install -r requirements.txt

# 下载 FFmpeg（约 160MB，仓库不含二进制）
python scripts/fetch_ffmpeg.py

# 启动
python run.py
```

> FFmpeg 也可手动放入 `resources/ffmpeg/`，或依赖系统 PATH。未安装 FFmpeg 程序仍可启动，但 QC 检测不可用。

---

## 功能

### 素材同步

- **三栏浏览**：项目导航 / 本地目录 / NAS 目录，一目了然
- **项目关联**：本地项目与 NAS 素材目录建立映射，支持归一化模糊匹配
- **SQLite 索引**：NAS 目录扫描结果本地缓存，避免重复遍历网络路径
- **文件操作**：复制、移动、重命名、新建、删除、拖拽

### 视频质检

| 检测项 | 说明 |
|:---|:---|
| 黑帧 | 全黑或近黑帧检测，区分硬切转场与异常黑帧 |
| 黑边 | 画面四周黑边检测（信噪比 + 梯度分析） |
| 静音 | 音频 RMS 检测，支持多阈值分级（忽略 / 警告 / 错误） |
| 一致性 | 多文件间的基本属性一致性校验 |
| 多版本对比 | 跨文件夹版本横向比较 |

- **单次解码复用**：`FrameScanner` 一次解码同时服务所有视觉检测器
- **Excel 报告导出**：检测结果明细，可直接交付审阅

---

## 项目结构

```
MediaNexus/
├── run.py                      # 开发入口
├── MediaNexus/         # 主程序包（PyInstaller 入口）
│   ├── constants.py            # 常量与配置
│   ├── config_manager.py       # 配置单例
│   ├── indexer.py              # NAS 索引器
│   ├── matcher.py              # 项目匹配
│   ├── workers.py              # 后台任务
│   ├── worker_manager.py       # Worker 生命周期
│   ├── qc_bridge.py            # QC 窗口桥接
│   └── ui/                     # 主窗口与各面板
├── core/                       # QC 核心算法（无 GUI 依赖）
├── qc_gui/                     # QC 窗口与控件
├── utils/                      # FFmpeg 管理、导出、存储等
├── scripts/                    # 工具脚本
├── assets/                     # 图标与静态资源
├── docs/                       # 用户文档
├── dev/                        # 开发手册
├── installer/                  # Inno Setup 安装器脚本
├── tests/                      # 冒烟测试
├── MediaNexus.spec     # PyInstaller 打包配置
└── config.json                 # 默认配置
```

### 模块边界

```
MediaNexus   →  主程序、项目管理、NAS 索引、UI
core                 →  QC 算法与检测编排（禁止依赖 PySide6）
qc_gui               →  QC 窗口、结果展示、交互
utils                →  FFmpeg、导出、存储、配置代理
```

> `core/` 保持纯 Python，不依赖 PySide6。UI 层不做耗时 I/O，必须交给 Worker。新增视觉检测优先复用 `FrameScanner`。

---

## 构建与发布

### PyInstaller 打包

```bash
python -m PyInstaller MediaNexus.spec --clean --noconfirm
```

输出：`dist/MediaNexus/`（onedir 分发）

### Inno Setup 安装包

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\MediaNexus-Setup.iss
```

输出：`dist/installer/MediaNexus-Setup-1.1.0.exe`

> 安装包不会删除 `%APPDATA%/MediaNexus` 下的用户配置。

---

## 测试

```bash
python -m pytest tests/ -q
```

覆盖：版本契约、索引器、并发稳定性、匹配器评分、FFmpeg 管理等。

| 修改范围 | 最低验证 |
|:---|:---|
| 配置 / 索引 / 匹配 | `pytest tests/ -q` |
| UI / 文件操作 | `python run.py` 手动验证 |
| QC 检测器 | 样本视频验证黑帧 / 黑边 / 静音 |
| 打包 | 启动 `dist/MediaNexus/MediaNexus.exe` |

---

## 配置

运行时配置存放于 `%APPDATA%/MediaNexus/`：

| 文件 | 用途 |
|:---|:---|
| `config.json` | 主配置（项目列表、预设、设置） |
| `nas_index.db` | NAS 目录索引（SQLite WAL） |

FFmpeg 查找优先级：系统 PATH → 用户手动指定 → `resources/ffmpeg/` → `%APPDATA%/MediaNexus/ffmpeg/bin`

---

## 文档

- [开发手册](dev/DevHandbook.md) — 架构细节、模块说明、已知问题
- [用户手册](docs/MediaNexus-Manual.html) — 功能使用指南

---

## 许可证

本项目仅供内部工具使用，未开源许可。如需使用请联系作者。
