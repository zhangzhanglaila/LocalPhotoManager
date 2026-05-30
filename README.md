# iPhoto 本地照片管理器

一个类似 macOS 照片应用的**文件夹原生**照片管理工具，支持 Windows、macOS 和 Linux。无需上传云端，直接管理本地照片和视频。

基于 [iPhotron](https://github.com/zhangzhanglaila/LocalPhotoManager) 开源项目的中文优化版本。

---

## 核心功能

| 功能 | 说明 |
|------|------|
| 照片浏览 | 网格视图、详情视图、幻灯片播放，支持缩放/平移 |
| 实况照片 | 自动配对 HEIC/MOV，支持播放 Live Photo 视频 |
| 照片地图 | 基于 GPS 数据在地图上标记照片位置，支持聚合和缩放 |
| 照片编辑 | 亮度/对比度/饱和度/曲线/裁剪/旋转/透视校正等 |
| 视频播放 | 内置视频播放器，支持旋转/裁剪/导出 |
| 人物识别 | 基于 InsightFace 的人脸检测和分组（需安装额外依赖） |
| 多图库管理 | 支持同时管理多个文件夹根目录 |
| 侧边栏过滤 | 按文件夹/相册勾选筛选显示的照片 |
| 元数据读取 | 支持 EXIF/GPS/拍摄日期等，基于 ExifTool |
| 跨平台 | Windows / macOS / Linux |

## 技术栈

- **语言：** Python 3.12+
- **GUI：** PySide6 (Qt 6)
- **数据库：** SQLite (WAL 模式)
- **图像处理：** Pillow, OpenCV, NumPy, rawpy
- **视频处理：** PyAV (FFmpeg)
- **地图渲染：** OsmAnd 矢量地图 + OpenGL
- **人脸检测：** InsightFace + ONNX Runtime
- **元数据：** ExifTool

## 安装

### 前置条件

- **Python 3.12+**
- **ExifTool**（必须，用于读取照片 EXIF/GPS 元数据）
  - Windows: `choco install exiftool` 或从 https://exiftool.org 下载
  - macOS: `brew install exiftool`
  - Linux: `sudo apt install libimage-exiftool-perl` 或 `sudo dnf install perl-Image-ExifTool`
- **FFmpeg**（必须，用于视频封面提取、元数据读取、视频导出）
  - Windows: `choco install ffmpeg` 或从 https://ffmpeg.org 下载
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` 或 `sudo dnf install ffmpeg`

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/zhangzhanglaila/LocalPhotoManager.git
cd LocalPhotoManager

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. 安装依赖
pip install -e .

# 4. 安装人脸检测依赖（如需"人物识别"功能）
pip install insightface onnxruntime
```

> **关于自动下载：**
>
> | 资源 | 大小 | 触发条件 | 下载来源 |
> |------|------|---------|----------|
> | 人脸模型 | ~300MB | 安装了 insightface 后，首次使用"人物识别" | InsightFace CDN（自动下载） |
> | 地图扩展 | ~975MB | 首次启动时弹窗提示 | 原始项目 GitHub Release（自动下载） |
>
> **注意：** 第 4 步不装的话，人脸功能完全不可用（不会自动下载模型）。
>
> **Linux 用户注意：** `rawpy` 依赖 `libraw`，安装前需先执行：
> ```bash
> sudo apt install libraw-dev    # Debian/Ubuntu
> sudo dnf install LibRaw-devel  # Fedora
> ```

### 国内用户特别说明

人脸模型和地图扩展需要从境外服务器下载，可能较慢或失败：

| 资源 | 解决方案 |
|------|----------|
| 人脸模型 (~300MB) | 使用代理，或从其他渠道获取模型文件后放到 `src/extension/models/` |
| 地图扩展 (~975MB) | 可跳过（自动降级为基础地图），或手动下载后放到项目目录 |

## 启动

```bash
iphoto-gui
```

或直接打开指定相册：

```bash
iphoto-gui /photos/LondonTrip
```

## 环境变量

| 变量名 | 说明 |
|--------|------|
| `IPHOTO_EXIFTOOL_PATH` | 指定 ExifTool 可执行文件路径 |
| `IPHOTO_FACE_MODEL_DIR` | 指定人脸模型目录（默认 `src/extension/models/`） |
| `IPHOTO_PREFER_OSMAND_NATIVE_WIDGET` | 设为 `0` 可禁用 OsmAnd 原生地图组件 |
| `IPHOTO_OSMAND_EXTENSION_ROOT` | 指定 OsmAnd 地图扩展目录 |

---

## 本版本修复与改进

### 一、性能优化

| 问题 | 修复前 | 修复后 | 修复方式 |
|------|--------|--------|----------|
| 实况照片配对卡死 | O(n²)，13068×3544 ≈ 4600 万次迭代，应用无响应 | O(n)，1.7 秒完成 | 预构建 `videos_by_stem` / `videos_by_folder` 字典索引，候选查找从 O(n) 降至 O(1) |
| 扫描期间点击任何按钮 | 主线程阻塞，弹出"Python 未响应" | 全部异步化，UI 始终流畅 | 路径验证移至 `GalleryLoadWorker` 后台线程；新增 `PathExistsCache` LRU 缓存（20,000 条） |
| 缩略图磁盘加载 | 同步 `QPixmap(disk_file)` 阻塞主线程 | `QRunnable` 后台加载，主线程只做 `QPixmap.fromImage()` | 新增 `ThumbnailDiskLoadTask(QRunnable)`，`QImage` 在后台线程创建 |
| 地图聚类 | 主线程遍历 16000 项 | >1000 项自动切换后台 `_ClusterWorker` 线程 | `_rebuild_photo_clusters()` 按数据量自动选择主线程/后台线程 |
| 地图渲染闪烁 | 每个缩略图到达就重绘一次，`clear_pixmaps()` 清空后逐个闪烁 | 双缓冲，一次性 blit 到屏幕 | `_MarkerLayer` 新增 `_back_buffer` + `_buffer_dirty` 标志 |
| 启动时界面卡死 | 地图 OpenGL 初始化 + 哈希遍历全部行 + 图库树级联加载阻塞主线程 | 懒加载 + O(1) 代次计数器 + 启动遮罩进度条 | 地图组件延迟初始化；`_snapshot_hash()` 改为代次计数器；拆分多步加载 |
| 同一图库 rescan 地图闪烁 | rescan 时清空所有缩略图再重新加载 | 保留已有缩略图，只更新变化部分 | 同一图库 rescan 时不发射 `thumbnailsInvalidated` 信号 |

### 二、Bug 修复

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 已删除文件仍显示在 All Photos | 本地文件已删除，缩略图仍可见，点击放大提示文件不存在 | All Photos 视图也验证路径存在性，后台线程过滤不存在的文件 |
| 单击照片无法打开详情页 | 单击无反应，必须双击才能放大查看 | 连接 `itemClicked` 信号到 `_on_asset_clicked`，单击/双击均可打开 |
| Escape 键直接关闭应用 | 按 Escape 无条件调用 `self.close()` 关闭整个窗口 | 移除无条件关闭，Escape 由 `AppShortcutManager` 管理，仅退出全屏 |
| 右键移除文件夹无响应 | 点击"移除"后无反应 | 连接 `excludeAlbumRequested` 信号 |
| 实况照片播放画面倒置 | Windows 上 180° 旋转被重复应用 | 修复旋转检测逻辑，Qt6 FFmpeg 后端自动处理旋转 |
| 实况照片只显示一张 | 配对时间差阈值过窄（3 秒），大量实况照片无法配对 | 阈值放宽至 5 秒；新增同文件名匹配逻辑 |
| 地图标记覆盖层不可见 | 覆盖层不透明，地图被完全遮挡 | 修复覆盖层透明度 |
| Ctrl+C 无法退出 | Qt `eventFilter` 内 `KeyboardInterrupt` 死循环 | Windows 后台看门线程正确处理 Ctrl+C 信号 |
| ExifTool 缺失导致崩溃 | 未安装 ExifTool 时提取元数据直接崩溃 | `ExternalToolError` 异常捕获，弹出中文警告对话框；Windows 自动检测路径 |

### 三、新功能

| 功能 | 说明 |
|------|------|
| 多图库共存 | 支持同时管理多个图库根目录，侧边栏显示所有已添加的图库 |
| 侧边栏文件夹过滤 | 可勾选/取消文件夹，按文件夹筛选显示的照片 |
| 详情页全屏按钮 | 详情页新增全屏按钮，支持沉浸式查看照片 |
| 照片地图面板 | 详情页新增地图面板，显示照片拍摄位置 |
| 扫描状态实时反馈 | 进度条 + 已扫描/总数，扫描过程透明可见 |
| 地图标记动态缩放 | 标记数字徽章随缩放级别动态调整大小 |
| 全局异常捕获 | 未处理的异常记录到日志文件，方便排查问题 |
| 全中文化 UI | 涉及 10+ 文件，包括状态栏、右键菜单、导出/分享提示、对话框、人物面板等 |

---

## 许可证

MIT License (原始项目许可证)

原始项目由 Haibin Zhao (OliverZhaohaibin) 创建。
