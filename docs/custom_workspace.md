# 自定义工作目录功能

## 功能说明

此功能允许用户将 iPhotron 的所有工作文件（索引、缓存、人脸数据等）存储在自定义位置，而不是照片文件夹内的 `.iPhoto` 目录。

### 目录结构

使用自定义工作目录后，文件结构如下：

```
<自定义工作目录>/
└── <照片库名称>/
    └── .iPhoto/
        ├── global_index.db          # 索引数据库
        ├── links.json               # Live Photo 配对数据
        ├── cache/
        │   ├── thumbs/             # 缩略图缓存
        │   └── shaders/            # 着色器缓存
        └── faces/
            ├── face_index.db       # 人脸索引
            ├── face_state.db       # 人脸状态
            └── thumbnails/         # 人脸缩略图
```

照片文件夹保持干净，只包含照片和视频：

```
<照片文件夹>/
├── 2024/
│   ├── 01/
│   │   ├── IMG_001.jpg
│   │   └── IMG_002.jpg
│   └── 02/
└── 2023/
    └── ...
```

## 配置方法

### 方法1：编辑设置文件

找到设置文件位置：
- **Windows**: `%APPDATA%\iPhoto\settings.json`
- **macOS**: `~/Library/Application Support/iPhoto/settings.json`
- **Linux**: `~/.config/iPhoto/settings.json`

添加或修改以下配置：

```json
{
  "workspace_base": "C:/iPhotronWorkspace"
}
```

### 方法2：使用迁移工具

```bash
# 查看帮助
python -m iPhoto.tools.migrate_workspace

# 执行迁移（示例）
python -m iPhoto.tools.migrate_workspace "D:/Photos" "C:/iPhotronWorkspace"

# 预览模式（不实际执行）
python -m iPhoto.tools.migrate_workspace "D:/Photos" "C:/iPhotronWorkspace" --dry-run
```

## 功能特性

- ✅ 照片文件夹完全干净，不生成任何 `.iPhoto` 文件
- ✅ 所有性能优化功能保留（索引、缓存、人脸数据）
- ✅ 支持多个照片库，每个库有独立工作空间
- ✅ 自动处理特殊字符（使用哈希值作为目录名）
- ✅ 提供数据迁移工具
- ✅ 兼容现有 `.iPhoto` 目录（自动检测）

## 性能影响

使用自定义工作目录**不会影响性能**，因为：
- SQLite 数据库操作相同
- 缩略图缓存机制相同
- 文件 I/O 模式相同
- 仅改变文件位置，不改变访问方式

## 回退方法

如需回退到传统模式（照片文件夹内的 `.iPhoto`）：

1. 关闭 iPhotron
2. 将自定义工作目录中的 `.iPhoto` 文件夹移回照片文件夹
3. 从设置文件中删除 `"workspace_base"` 配置
4. 重启 iPhotron
