# LocalPhotoManager

本地照片管理器 —— 一个类似 macOS 照片应用的文件夹原生照片管理工具，支持 Windows、macOS 和 Linux。

基于 [iPhotron](https://github.com/OliverZhaohaibin/iPhotron-LocalPhotoAlbumManager) 开源项目的中文优化版本。

---

## 本版本修复与改进

### 1. ExifTool 缺失导致应用崩溃

**问题：** 未安装 ExifTool 时，应用在提取照片元数据（GPS、尺寸、拍摄日期等）时直接崩溃退出。

**修复：**
- 创建 `exiftool.bat` 包装脚本，支持通过 conda 环境调用 ExifTool
- 添加 `ExternalToolError` 异常捕获机制，缺失时弹出中文警告对话框而非崩溃
- 支持通过环境变量 `IPHOTO_EXIFTOOL_PATH` 指定 ExifTool 路径

### 2. 应用启动时界面卡死（"Python 未响应"）

**问题：** 启动时多个重操作阻塞主线程：地图组件 OpenGL 初始化、照片列表哈希计算遍历全部行（万张照片 = 万次 SQLite 查询）、图库树刷新级联触发重复加载。

**修复：**
- 将地图组件改为懒加载模式，启动时仅显示占位文字
- 修复 `set_map_runtime()` 在启动期间绕过懒加载直接触发 `_rebuild_map_widget()` 的问题
- 修复 `_snapshot_hash()` 遍历全部行导致 O(N) 数据库查询的问题，改为 O(1) 代次计数器
- 启动期间跳过 `_on_library_tree_updated()` 的重复加载级联
- 添加启动加载遮罩（进度条 + 阶段文字），将启动流程拆分为多步，让用户看到加载进度

### 3. 全部英文 UI 翻译为中文

**问题：** 界面中存在大量英文文本，对中文用户不友好。

**修复：** 涉及 10+ 个文件，包括：
- 状态栏控制器
- 右键菜单
- 导出功能提示
- 分享功能提示
- 对话框（绑定图库提示等）
- 相册侧边栏菜单
- 相册名称验证提示
- 人物面板
- 信息面板（人脸分配）

### 4. 全局异常捕获

**改进：** 添加全局异常钩子，未处理的异常会被记录到日志文件，方便排查问题。

### 5. 实况照片（Live Photo）修复

**问题 1：** 点击实况照片播放视频时画面倒置。

**修复：** 修复 Windows 平台上 180° 旋转检测逻辑。Qt6 FFmpeg 后端已自动处理旋转，但代码重复应用了 180° 旋转，导致画面倒置。

**问题 2：** 只显示一张实况照片，明明有很多。

**修复：**
- 将配对时间差阈值从 3 秒放宽到 5 秒
- 新增同文件名匹配逻辑：iPhone 实况照片的图片和视频总是同名（如 `IMG_1234.HEIC` + `IMG_1234.MOV`），即使时间戳不同也能正确配对

---

## 环境变量

| 变量名 | 说明 |
|--------|------|
| `IPHOTO_EXIFTOOL_PATH` | 指定 ExifTool 可执行文件路径 |
| `IPHOTO_PREFER_OSMAND_NATIVE_WIDGET` | 设为 `0` 可禁用 OsmAnd 原生地图组件 |

---

## 开发者安装

```bash
pip install -e .
```

## 启动

```bash
iphoto-gui
```

或直接打开指定相册：

```bash
iphoto-gui /photos/LondonTrip
```

---

## 许可证

MIT License (原始项目许可证)

原始项目由 Haibin Zhao (OliverZhaohaibin) 创建。
