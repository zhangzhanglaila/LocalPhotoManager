# 🚀 iPhotron v6.x 新功能实现方案

> 版本 1.0 · 2026-06-03
>
> 本文档定义三个新功能的详细实现方案：**OCR 文字搜索**、**地图时间线/轨迹**、**人脸+地图联动**。
> 每个功能包含架构设计、文件清单、实现步骤、数据库变更和测试要点。

---

## 目录

1. [功能一：OCR 文字搜索](#1-功能一ocr-文字搜索)
2. [功能二：地图时间线/轨迹](#2-功能二地图时间线轨迹)
3. [功能三：人脸+地图联动](#3-功能三人脸地图联动)
4. [开发顺序与里程碑](#4-开发顺序与里程碑)
5. [依赖变更汇总](#5-依赖变更汇总)

---

## 1. 功能一：OCR 文字搜索

### 1.1 功能概述

在扫描照片时自动提取图片中的文字（截图、文档、路牌等），存入 SQLite FTS5 全文索引，用户可在搜索框中输入文字搜索包含该文字的照片。

**前置条件**：已有 `docs/requirements/face&OCR/development.md` 中定义的 AI 子系统架构（方案 B）。

### 1.2 技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| OCR 引擎 | RapidOCR (PP-OCRv5) | 检测+识别一体化管线 |
| 推理引擎 | ONNX Runtime | 支持 CPU/CUDA/OpenVINO |
| 全文索引 | SQLite FTS5 | 内置，无需额外依赖 |
| 模型下载 | huggingface-hub | 自动下载 PP-OCRv5 模型 |

### 1.3 数据库设计

**新建数据库**：`ocr_index.db`（与 `global_index.db`、`face_index.db` 并列）

```sql
-- OCR 文字区域表
CREATE TABLE IF NOT EXISTS ocr_regions (
    rowid          INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id       TEXT NOT NULL,
    asset_rel      TEXT NOT NULL,
    text           TEXT NOT NULL,
    confidence     REAL NOT NULL,
    box_x          REAL NOT NULL,
    box_y          REAL NOT NULL,
    box_w          REAL NOT NULL,
    box_h          REAL NOT NULL,
    image_width    INTEGER NOT NULL,
    image_height   INTEGER NOT NULL,
    detected_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(asset_id, text, box_x, box_y)
);

CREATE INDEX IF NOT EXISTS idx_ocr_regions_asset ON ocr_regions(asset_id);

-- FTS5 全文索引
CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(
    text,
    content='ocr_regions',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

-- 同步触发器
CREATE TRIGGER IF NOT EXISTS ocr_ai AFTER INSERT ON ocr_regions BEGIN
    INSERT INTO ocr_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS ocr_ad AFTER DELETE ON ocr_regions BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS ocr_au AFTER UPDATE ON ocr_regions BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO ocr_fts(rowid, text) VALUES (new.rowid, new.text);
END;
```

### 1.4 新增文件清单

```
src/iPhoto/
├── ai/                                    # AI 子系统（复用 development.md 规划）
│   ├── __init__.py
│   ├── config.py                          # AI 配置常量
│   ├── compute_backend.py                 # ONNX Runtime EP 选择
│   │
│   ├── ocr/                               # OCR 子模块
│   │   ├── __init__.py
│   │   ├── ocr_engine.py                  # RapidOCR 引擎封装
│   │   └── models.py                      # OCRRegion dataclass
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── ocr_database.py                # ocr_index.db 连接管理
│   │   └── ocr_repository.py              # OCR 仓储（CRUD + FTS5 搜索）
│   │
│   └── workers/
│       ├── __init__.py
│       └── ocr_worker.py                  # OCR 后台 Worker (QRunnable)
│
├── application/ports/
│   └── ocr.py                             # 🆕 OCRArchivePort Protocol
│
└── gui/ui/widgets/
    └── ocr_search_panel.py                # 🆕 OCR 搜索结果面板
```

### 1.5 核心类设计

#### 1.5.1 OCR 引擎 (`ai/ocr/ocr_engine.py`)

```python
class OCREngine:
    """RapidOCR 封装，惰性加载模型"""

    def __init__(self, model_cache_dir: Path | None = None):
        self._engine = None
        self._lock = threading.Lock()
        self._cache_dir = model_cache_dir

    def _ensure_loaded(self) -> None:
        """首次调用时加载模型（~10s），后续复用"""
        if self._engine is not None:
            return
        with self._lock:
            if self._engine is not None:
                return
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR(
                det_model_dir=str(self._cache_dir / "ppocrv5_det"),
                rec_model_dir=str(self._cache_dir / "ppocrv5_rec"),
                cls_model_dir=str(self._cache_dir / "ppocrv5_cls"),
            )

    def extract_text(self, image_path: Path) -> list[OCRRegion]:
        """提取图片中的所有文字区域"""
        self._ensure_loaded()
        result, _ = self._engine(str(image_path))
        if result is None:
            return []
        regions = []
        for box, text, confidence in result:
            # box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            x_min = min(p[0] for p in box)
            y_min = min(p[1] for p in box)
            x_max = max(p[0] for p in box)
            y_max = max(p[1] for p in box)
            regions.append(OCRRegion(
                text=text,
                confidence=confidence,
                box_x=x_min, box_y=y_min,
                box_w=x_max - x_min, box_h=y_max - y_min,
            ))
        return regions
```

#### 1.5.2 OCR 仓储 (`ai/db/ocr_repository.py`)

```python
class OCRRepository:
    """OCR 文字存储与 FTS5 搜索"""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._local = threading.local()
        self._create_schema()

    def store_regions(self, asset_id: str, asset_rel: str,
                      regions: list[OCRRegion],
                      image_width: int, image_height: int) -> None:
        """存储一张图片的所有 OCR 区域"""
        conn = self._get_connection()
        conn.executemany("""
            INSERT OR REPLACE INTO ocr_regions
            (asset_id, asset_rel, text, confidence, box_x, box_y, box_w, box_h,
             image_width, image_height)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(asset_id, asset_rel, r.text, r.confidence,
               r.box_x, r.box_y, r.box_w, r.box_h,
               image_width, image_height) for r in regions])
        conn.commit()

    def search(self, query: str, limit: int = 100) -> list[OCRSearchResult]:
        """FTS5 全文搜索"""
        conn = self._get_connection()
        rows = conn.execute("""
            SELECT r.asset_id, r.asset_rel, r.text, r.confidence,
                   rank, snippet(ocr_fts, 0, '<b>', '</b>', '...', 32) as snippet
            FROM ocr_fts
            JOIN ocr_regions r ON ocr_fts.rowid = r.rowid
            WHERE ocr_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
        return [OCRSearchResult(**dict(r)) for r in rows]

    def get_asset_ids_with_ocr(self) -> set[str]:
        """获取已做 OCR 的 asset_id 集合"""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT DISTINCT asset_id FROM ocr_regions"
        ).fetchall()
        return {r['asset_id'] for r in rows}

    def delete_by_asset(self, asset_id: str) -> None:
        """删除某图片的所有 OCR 数据"""
        conn = self._get_connection()
        conn.execute("DELETE FROM ocr_regions WHERE asset_id = ?", (asset_id,))
        conn.commit()
```

#### 1.5.3 OCR Worker (`ai/workers/ocr_worker.py`)

```python
class OCRWorkerSignals(QObject):
    progress = Signal(int, int)        # (current, total)
    chunk_ready = Signal(list)          # list[AssetRow] 需要 OCR 的新图片
    finished = Signal()
    error = Signal(str)

class OCRWorker(QRunnable):
    """后台 OCR 扫描 Worker"""

    def __init__(self, ocr_engine: OCREngine,
                 ocr_repository: OCRRepository,
                 library_root: Path):
        super().__init__()
        self.signals = OCRWorkerSignals()
        self._engine = ocr_engine
        self._repo = ocr_repository
        self._library_root = library_root
        self._queue: list[AssetRow] = []
        self._finished = False

    @Slot(list)
    def enqueue_rows(self, rows: list[AssetRow]) -> None:
        """接收扫描批次，过滤需要 OCR 的图片"""
        image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.heic'}
        filtered = [r for r in rows
                    if Path(r.asset_rel).suffix.lower() in image_exts]
        self._queue.extend(filtered)

    @Slot()
    def finish_input(self) -> None:
        self._finished = True

    def run(self) -> None:
        """处理队列中的所有图片"""
        processed = 0
        while self._queue or not self._finished:
            if not self._queue:
                QThread.msleep(100)
                continue
            batch = self._queue[:16]
            self._queue = self._queue[16:]
            for row in batch:
                try:
                    image_path = self._library_root / row.asset_rel
                    regions = self._engine.extract_text(image_path)
                    if regions:
                        self._repo.store_regions(
                            row.asset_id, row.asset_rel,
                            regions, row.width or 0, row.height or 0
                        )
                    processed += 1
                    self.signals.progress.emit(processed, 0)
                except Exception as e:
                    logging.warning(f"OCR failed for {row.asset_rel}: {e}")
        self.signals.finished.emit()
```

### 1.6 扫描集成

**修改文件**：`src/iPhoto/library/scan_coordinator.py`

```python
# 在 start_scanning() 中添加 OCR Worker
def start_scanning(self, ...):
    # ... 现有代码 ...
    self._face_worker = FaceScanWorker(...)
    self._ocr_worker = OCRWorker(...)              # 🆕
    self._ocr_thread = QThread()                   # 🆕
    self._ocr_worker.moveToThread(self._ocr_thread) # 🆕

    # 连接信号
    self._scan_worker.chunkArrived.connect(self._face_worker.enqueue_rows)
    self._scan_worker.chunkArrived.connect(self._ocr_worker.enqueue_rows)  # 🆕
    self._scan_worker.scanFinished.connect(self._face_worker.finish_input)
    self._scan_worker.scanFinished.connect(self._ocr_worker.finish_input)  # 🆕

    self._ocr_thread.start()                       # 🆕
```

### 1.7 搜索集成

**修改文件**：`src/iPhoto/agent/services/search_service.py`

```python
class SearchService:
    def __init__(self, embedding_service, asset_repository,
                 embedding_repository, ocr_repository=None):  # 🆕 可选注入
        self._ocr_repo = ocr_repository

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        results = []

        # 1. CLIP 语义搜索（现有逻辑）
        clip_results = self._clip_search(query, limit)
        results.extend(clip_results)

        # 2. OCR 文字搜索（🆕）
        if self._ocr_repo:
            ocr_hits = self._ocr_repo.search(query, limit=limit)
            for hit in ocr_hits:
                results.append(SearchResult(
                    asset_id=hit.asset_id,
                    asset_rel=hit.asset_rel,
                    score=hit.confidence,
                    caption=hit.snippet,
                    metadata={"source": "ocr"}
                ))

        # 3. 去重合并（同一图片取最高分）
        seen = {}
        for r in results:
            key = r.asset_id
            if key not in seen or r.score > seen[key].score:
                seen[key] = r
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)[:limit]
```

### 1.8 实现步骤

| 步骤 | 任务 | 预计时间 | 依赖 |
|------|------|----------|------|
| 1 | 添加 `rapidocr-onnxruntime` 依赖到 `pyproject.toml` | 0.5h | 无 |
| 2 | 创建 `ai/ocr/ocr_engine.py` - RapidOCR 封装 | 1d | 步骤 1 |
| 3 | 创建 `ai/db/ocr_database.py` - ocr_index.db 连接管理 | 0.5d | 无 |
| 4 | 创建 `ai/db/ocr_repository.py` - FTS5 仓储 | 1d | 步骤 3 |
| 5 | 创建 `ai/workers/ocr_worker.py` - 后台 Worker | 1d | 步骤 2, 4 |
| 6 | 修改 `scan_coordinator.py` - 集成 OCR Worker | 0.5d | 步骤 5 |
| 7 | 修改 `search_service.py` - 合并 OCR 搜索结果 | 0.5d | 步骤 4 |
| 8 | 创建 `gui/ui/widgets/ocr_search_panel.py` - 搜索结果 UI | 1d | 步骤 7 |
| 9 | 测试：单元测试 + 集成测试 | 1d | 步骤 1-8 |
| **合计** | | **~7 天** | |

---

## 2. 功能二：地图时间线/轨迹

### 2.1 功能概述

在地图上绘制照片拍摄的时间轨迹线，支持时间滑块过滤，按天/周/月聚合轨迹，生成旅行回忆。

### 2.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    地图时间线架构                             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ PhotoMapView (现有)                                  │   │
│  │  ├── _MarkerLayer (现有标记层)                        │   │
│  │  ├── _TrailLayer (🆕 轨迹层)                         │   │
│  │  │    ├── 轨迹线 (QPainter drawPolyline)             │   │
│  │  │    ├── 时间节点标记                                │   │
│  │  │    └── 日期标注                                    │   │
│  │  └── _TimelineSlider (🆕 时间滑块控件)                │   │
│  │       ├── 日期范围选择                                │   │
│  │       ├── 聚合粒度切换 (天/周/月)                     │   │
│  │       └── 播放/暂停按钮                               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ TrailController (🆕 轨迹控制器)                       │   │
│  │  ├── 按时间范围过滤带 GPS 的照片                      │   │
│  │  ├── 按天/周/月聚合轨迹段                             │   │
│  │  ├── 计算轨迹点的屏幕坐标                             │   │
│  │  └── 视口裁剪优化                                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 数据模型

```python
# src/iPhoto/gui/ui/models/trail_models.py

@dataclass(frozen=True)
class TrailPoint:
    """轨迹上的一个点"""
    asset_id: str
    asset_rel: str
    latitude: float
    longitude: float
    timestamp: datetime
    thumbnail_path: Path | None = None

@dataclass(frozen=True)
class TrailSegment:
    """一段连续轨迹（同一天/周/月内）"""
    points: list[TrailPoint]
    start_time: datetime
    end_time: datetime
    color: QColor  # 每段不同颜色

@dataclass(frozen=True)
class TrailData:
    """完整的轨迹数据"""
    segments: list[TrailSegment]
    total_photos: int
    date_range: tuple[datetime, datetime]
```

### 2.4 新增文件清单

```
src/iPhoto/
├── gui/ui/
│   ├── models/
│   │   └── trail_models.py                # 🆕 TrailPoint, TrailSegment, TrailData
│   │
│   └── widgets/
│       ├── trail_layer.py                 # 🆕 轨迹绘制层
│       └── timeline_slider.py             # 🆕 时间滑块控件
│
├── application/services/
│   └── trail_service.py                   # 🆕 轨迹数据服务
│
└── application/ports/
    └── trail.py                           # 🆕 TrailServicePort Protocol
```

### 2.5 核心类设计

#### 2.5.1 轨迹服务 (`application/services/trail_service.py`)

```python
class TrailService:
    """轨迹数据构建与过滤"""

    def __init__(self, asset_repository: AssetRepositoryPort,
                 location_service: LocationAssetServicePort):
        self._asset_repo = asset_repository
        self._location_service = location_service

    def build_trail(self, date_from: datetime | None = None,
                    date_to: datetime | None = None,
                    granularity: str = "day") -> TrailData:
        """
        构建轨迹数据

        Args:
            date_from: 开始日期（None=最早）
            date_to: 结束日期（None=最新）
            granularity: 聚合粒度 "day" | "week" | "month"
        """
        # 1. 获取带 GPS 的照片，按时间排序
        geotagged = self._location_service.list_geotagged_assets()
        if date_from:
            geotagged = [a for a in geotagged if a.timestamp >= date_from]
        if date_to:
            geotagged = [a for a in geotagged if a.timestamp <= date_to]
        geotagged.sort(key=lambda a: a.timestamp)

        # 2. 按粒度分组
        segments = self._group_by_granularity(geotagged, granularity)

        # 3. 构建轨迹段
        colors = self._generate_colors(len(segments))
        trail_segments = []
        for i, (key, group) in enumerate(segments):
            points = [TrailPoint(
                asset_id=a.asset_id,
                asset_rel=a.asset_rel,
                latitude=a.latitude,
                longitude=a.longitude,
                timestamp=a.timestamp,
            ) for a in group]
            trail_segments.append(TrailSegment(
                points=points,
                start_time=points[0].timestamp,
                end_time=points[-1].timestamp,
                color=colors[i],
            ))

        all_points = [p for seg in trail_segments for p in seg.points]
        return TrailData(
            segments=trail_segments,
            total_photos=len(all_points),
            date_range=(all_points[0].timestamp, all_points[-1].timestamp)
                if all_points else (datetime.now(), datetime.now()),
        )

    def _group_by_granularity(self, assets, granularity):
        """按天/周/月分组，同组内超过 24h 间隔则拆分"""
        groups = {}
        for asset in assets:
            if granularity == "day":
                key = asset.timestamp.date()
            elif granularity == "week":
                key = asset.timestamp.date() - timedelta(days=asset.timestamp.weekday())
            else:  # month
                key = asset.timestamp.replace(day=1).date()
            groups.setdefault(key, []).append(asset)

        # 拆分间隔超过 24h 的段
        result = {}
        for key, group in groups.items():
            sub_groups = []
            current = [group[0]]
            for prev, curr in zip(group, group[1:]):
                if (curr.timestamp - prev.timestamp).total_seconds() > 86400:
                    sub_groups.append(current)
                    current = [curr]
                else:
                    current.append(curr)
            sub_groups.append(current)
            for i, sg in enumerate(sub_groups):
                result[(key, i)] = sg
        return result.items()

    def _generate_colors(self, count: int) -> list[QColor]:
        """生成渐变色序列"""
        colors = []
        for i in range(count):
            hue = int(360 * i / max(count, 1))
            colors.append(QColor.fromHsv(hue, 200, 220))
        return colors
```

#### 2.5.2 轨迹绘制层 (`gui/ui/widgets/trail_layer.py`)

```python
class TrailLayer(QWidget):
    """地图轨迹叠加层"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trail_data: TrailData | None = None
        self._map_widget: MapGLWidget | MapWidget | None = None
        self._visible_segments: set[int] = set()  # 当前可见的段索引
        self._highlighted_point: TrailPoint | None = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_trail(self, trail: TrailData) -> None:
        self._trail_data = trail
        self._visible_segments = set(range(len(trail.segments)))
        self.update()

    def set_map_widget(self, widget) -> None:
        self._map_widget = widget

    def paintEvent(self, event) -> None:
        if not self._trail_data or not self._map_widget:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        for idx in self._visible_segments:
            segment = self._trail_data.segments[idx]
            self._paint_segment(painter, segment)

        if self._highlighted_point:
            self._paint_highlight(painter, self._highlighted_point)

    def _paint_segment(self, painter: QPainter, segment: TrailSegment) -> None:
        """绘制一段轨迹线"""
        pen = QPen(segment.color, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        points = []
        for tp in segment.points:
            screen = self._map_widget.project_lonlat(tp.longitude, tp.latitude)
            if screen:
                points.append(screen)

        if len(points) >= 2:
            # 绘制轨迹线
            path = QPainterPath()
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            painter.drawPath(path)

            # 绘制时间节点（首尾和每天的第一个点）
            painter.setBrush(segment.color)
            for i, p in enumerate(points):
                if i == 0 or i == len(points) - 1:
                    painter.drawEllipse(p, 6, 6)
                else:
                    painter.drawEllipse(p, 3, 3)

    def _paint_highlight(self, painter: QPainter, point: TrailPoint) -> None:
        """绘制高亮点（鼠标悬停时）"""
        screen = self._map_widget.project_lonlat(point.longitude, point.latitude)
        if screen:
            painter.setPen(QPen(Qt.white, 3))
            painter.setBrush(QColor(255, 100, 0, 200))
            painter.drawEllipse(screen, 10, 10)
```

#### 2.5.3 时间滑块控件 (`gui/ui/widgets/timeline_slider.py`)

```python
class TimelineSlider(QWidget):
    """时间范围滑块 + 聚合粒度切换"""

    rangeChanged = Signal(datetime, datetime)
    granularityChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_date: datetime = datetime(2000, 1, 1)
        self._end_date: datetime = datetime.now()
        self._current_start: datetime = self._start_date
        self._current_end: datetime = self._end_date
        self._granularity: str = "day"

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # 日期标签
        self._start_label = QLabel(self._format_date(self._current_start))
        self._end_label = QLabel(self._format_date(self._current_end))

        # 范围滑块
        self._slider = QRangeSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(1000)
        self._slider.setValue((0, 1000))
        self._slider.valueChanged.connect(self._on_slider_changed)

        # 聚合粒度按钮
        self._btn_day = QPushButton("日")
        self._btn_week = QPushButton("周")
        self._btn_month = QPushButton("月")
        for btn in [self._btn_day, self._btn_week, self._btn_month]:
            btn.setCheckable(True)
            btn.setFixedWidth(32)
        self._btn_day.setChecked(True)
        self._btn_day.clicked.connect(lambda: self._set_granularity("day"))
        self._btn_week.clicked.connect(lambda: self._set_granularity("week"))
        self._btn_month.clicked.connect(lambda: self._set_granularity("month"))

        # 布局
        layout.addWidget(self._start_label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._end_label)
        layout.addWidget(self._btn_day)
        layout.addWidget(self._btn_week)
        layout.addWidget(self._btn_month)

    def set_date_range(self, start: datetime, end: datetime) -> None:
        self._start_date = start
        self._end_date = end
        self._current_start = start
        self._current_end = end
        self._start_label.setText(self._format_date(start))
        self._end_label.setText(self._format_date(end))

    def _on_slider_changed(self, low, high):
        total = (self._end_date - self._start_date).total_seconds()
        self._current_start = self._start_date + timedelta(seconds=total * low / 1000)
        self._current_end = self._start_date + timedelta(seconds=total * high / 1000)
        self._start_label.setText(self._format_date(self._current_start))
        self._end_label.setText(self._format_date(self._current_end))
        self.rangeChanged.emit(self._current_start, self._current_end)

    def _set_granularity(self, g: str):
        self._granularity = g
        for btn in [self._btn_day, self._btn_week, self._btn_month]:
            btn.setChecked(False)
        {"day": self._btn_day, "week": self._btn_week, "month": self._btn_month}[g].setChecked(True)
        self.granularityChanged.emit(g)

    def _format_date(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")
```

### 2.6 PhotoMapView 集成

**修改文件**：`src/iPhoto/gui/ui/widgets/photo_map_view.py`

```python
class PhotoMapView(QWidget):
    def __init__(self, ...):
        # ... 现有代码 ...
        self._trail_layer = TrailLayer(self)           # 🆕
        self._timeline_slider = TimelineSlider(self)   # 🆕
        self._trail_service: TrailService | None = None

        # 布局：地图 + 底部滑块
        self._layout.addWidget(self._timeline_slider)  # 🆕

        # 连接信号
        self._timeline_slider.rangeChanged.connect(self._on_time_range_changed)
        self._timeline_slider.granularityChanged.connect(self._on_granularity_changed)

    def set_trail_service(self, service: TrailService) -> None:
        self._trail_service = service

    @Slot(datetime, datetime)
    def _on_time_range_changed(self, start: datetime, end: datetime) -> None:
        if self._trail_service:
            trail = self._trail_service.build_trail(start, end, self._granularity)
            self._trail_layer.set_trail(trail)
            self._trail_layer.update()

    @Slot(str)
    def _on_granularity_changed(self, g: str) -> None:
        self._granularity = g
        self._on_time_range_changed(
            self._timeline_slider._current_start,
            self._timeline_slider._current_end
        )
```

### 2.7 实现步骤

| 步骤 | 任务 | 预计时间 | 依赖 |
|------|------|----------|------|
| 1 | 创建 `gui/ui/models/trail_models.py` - 数据模型 | 0.5d | 无 |
| 2 | 创建 `application/services/trail_service.py` - 轨迹构建服务 | 1.5d | 步骤 1 |
| 3 | 创建 `gui/ui/widgets/trail_layer.py` - 轨迹绘制层 | 1.5d | 步骤 1 |
| 4 | 创建 `gui/ui/widgets/timeline_slider.py` - 时间滑块 | 1d | 无 |
| 5 | 修改 `photo_map_view.py` - 集成轨迹层和滑块 | 1d | 步骤 2-4 |
| 6 | 视口裁剪优化（只绘制可见轨迹段） | 0.5d | 步骤 3 |
| 7 | 测试：单元测试 + 性能测试（万级轨迹点） | 1d | 步骤 1-6 |
| **合计** | | **~7 天** | |

---

## 3. 功能三：人脸+地图联动

### 3.1 功能概述

选择某个人物后，在地图上只显示该人物的照片位置，地图标记显示人脸缩略图，支持"这个人去过哪里"一键查看。

### 3.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    人脸+地图联动架构                          │
│                                                             │
│  ┌──────────────┐    person_id     ┌──────────────────┐    │
│  │ People       │ ────────────────→│ PersonMapFilter  │    │
│  │ Dashboard    │                  │ (🆕 过滤器)       │    │
│  └──────────────┘                  └────────┬─────────┘    │
│                                             │               │
│                                             │ 过滤后的       │
│                                             │ GeotaggedAsset│
│                                             ▼               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ PhotoMapView                                          │  │
│  │  ├── MarkerController.set_assets(过滤后)              │  │
│  │  ├── _MarkerLayer: 显示人脸缩略图                     │  │
│  │  └── _TrailLayer: 显示该人物轨迹（复用功能二）         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ PeopleService (现有)                                  │  │
│  │  ├── cluster_asset_ids(person_id) → set[str]         │  │
│  │  └── list_clusters() → list[PersonSummary]           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 新增文件清单

```
src/iPhoto/
├── application/services/
│   └── person_map_filter.py               # 🆕 人物地图过滤服务
│
├── gui/ui/widgets/
│   ├── person_map_panel.py                # 🆕 人物选择面板（嵌入地图侧边栏）
│   └── person_marker_delegate.py          # 🆕 人脸缩略图标记绘制器
│
└── application/ports/
    └── person_map.py                      # 🆕 PersonMapFilterPort Protocol
```

### 3.4 核心类设计

#### 3.4.1 人物地图过滤服务 (`application/services/person_map_filter.py`)

```python
class PersonMapFilter:
    """根据人物过滤地图上的照片"""

    def __init__(self, people_service: PeopleService,
                 location_service: LocationAssetServicePort,
                 asset_repository: AssetRepositoryPort):
        self._people_service = people_service
        self._location_service = location_service
        self._asset_repo = asset_repository
        self._active_person_id: str | None = None
        self._all_geotagged: list[GeotaggedAsset] = []

    def set_all_geotagged(self, assets: list[GeotaggedAsset]) -> None:
        """设置全量带 GPS 的照片列表"""
        self._all_geotagged = assets

    @property
    def active_person_id(self) -> str | None:
        return self._active_person_id

    def filter_by_person(self, person_id: str | None) -> list[GeotaggedAsset]:
        """
        按人物过滤带 GPS 的照片

        Args:
            person_id: 人物 ID，None 表示显示全部

        Returns:
            过滤后的 GeotaggedAsset 列表
        """
        self._active_person_id = person_id

        if person_id is None:
            return self._all_geotagged

        # 获取该人物的所有 asset_id
        person_asset_ids = self._people_service.cluster_asset_ids(person_id)
        if not person_asset_ids:
            return []

        # 过滤带 GPS 的照片
        return [a for a in self._all_geotagged
                if a.asset_id in person_asset_ids]

    def get_person_locations(self, person_id: str) -> list[PersonLocation]:
        """
        获取某人物的照片位置汇总

        Returns:
            按位置分组的照片统计
        """
        geotagged = self.filter_by_person(person_id)
        location_groups: dict[str, list[GeotaggedAsset]] = {}
        for asset in geotagged:
            key = asset.location_name or f"{asset.latitude:.2f},{asset.longitude:.2f}"
            location_groups.setdefault(key, []).append(asset)

        return [PersonLocation(
            location_name=key,
            photo_count=len(assets),
            latitude=assets[0].latitude,
            longitude=assets[0].longitude,
            date_range=(min(a.timestamp for a in assets),
                       max(a.timestamp for a in assets)),
        ) for key, assets in location_groups.items()]

    def get_person_summary(self, person_id: str) -> PersonMapSummary:
        """获取人物地图摘要"""
        locations = self.get_person_locations(person_id)
        filtered = self.filter_by_person(person_id)
        return PersonMapSummary(
            person_id=person_id,
            total_photos=len(filtered),
            unique_locations=len(locations),
            locations=locations,
        )
```

#### 3.4.2 数据模型

```python
# src/iPhoto/application/dtos.py (追加)

@dataclass(frozen=True)
class PersonLocation:
    """人物在某位置的照片统计"""
    location_name: str
    photo_count: int
    latitude: float
    longitude: float
    date_range: tuple[datetime, datetime]

@dataclass(frozen=True)
class PersonMapSummary:
    """人物地图摘要"""
    person_id: str
    total_photos: int
    unique_locations: int
    locations: list[PersonLocation]
```

#### 3.4.3 人物选择面板 (`gui/ui/widgets/person_map_panel.py`)

```python
class PersonMapPanel(QWidget):
    """地图侧边栏的人物选择面板"""

    personSelected = Signal(str)      # person_id
    personDeselected = Signal()       # 取消选择

    def __init__(self, people_service: PeopleService, parent=None):
        super().__init__(parent)
        self._people_service = people_service
        self._selected_person_id: str | None = None
        self._setup_ui()
        self._load_persons()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # 标题
        title = QLabel("按人物筛选")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # 搜索框
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索人物...")
        self._search.textChanged.connect(self._filter_list)
        layout.addWidget(self._search)

        # 人物列表（网格显示头像）
        self._scroll = QScrollArea()
        self._grid = QWidget()
        self._grid_layout = QGridLayout(self._grid)
        self._scroll.setWidget(self._grid)
        self._scroll.setWidgetResizable(True)
        layout.addWidget(self._scroll, 1)

        # "显示全部"按钮
        self._btn_all = QPushButton("显示全部")
        self._btn_all.clicked.connect(self._on_deselect)
        layout.addWidget(self._btn_all)

    def _load_persons(self):
        """加载人物列表"""
        summaries = self._people_service.list_clusters(include_hidden=False)
        self._person_cards: list[PersonCard] = []

        for i, s in enumerate(summaries):
            card = PersonCard(s)
            card.clicked.connect(lambda pid=s.person_id: self._on_select(pid))
            self._grid_layout.addWidget(card, i // 4, i % 4)
            self._person_cards.append(card)

    def _on_select(self, person_id: str):
        self._selected_person_id = person_id
        # 高亮选中的卡片
        for card in self._person_cards:
            card.set_selected(card.person_id == person_id)
        self.personSelected.emit(person_id)

    def _on_deselect(self):
        self._selected_person_id = None
        for card in self._person_cards:
            card.set_selected(False)
        self.personDeselected.emit()

    def _filter_list(self, text: str):
        for card in self._person_cards:
            card.setVisible(text.lower() in card.person_name.lower())


class PersonCard(QFrame):
    """人物头像卡片"""
    clicked = Signal(str)

    def __init__(self, summary: PersonSummary, parent=None):
        super().__init__(parent)
        self.person_id = summary.person_id
        self.person_name = summary.name or "未命名"
        self._setup_ui(summary)

    def _setup_ui(self, s: PersonSummary):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.setFixedSize(80, 100)
        self.setCursor(Qt.PointingHandCursor)

        # 头像
        avatar = QLabel()
        avatar.setFixedSize(64, 64)
        avatar.setScaledContents(True)
        if s.thumbnail_path and s.thumbnail_path.exists():
            avatar.setPixmap(QPixmap(str(s.thumbnail_path)))
        else:
            avatar.setText("👤")
            avatar.setAlignment(Qt.AlignCenter)
        layout.addWidget(avatar, 0, Qt.AlignCenter)

        # 名字
        name = QLabel(self.person_name)
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet("font-size: 11px;")
        layout.addWidget(name)

    def set_selected(self, selected: bool):
        if selected:
            self.setStyleSheet("PersonCard { border: 2px solid #2196F3; border-radius: 6px; }")
        else:
            self.setStyleSheet("PersonCard { border: 1px solid #ccc; border-radius: 6px; }")

    def mousePressEvent(self, event):
        self.clicked.emit(self.person_id)
```

#### 3.4.4 PhotoMapView 集成

**修改文件**：`src/iPhoto/gui/ui/widgets/photo_map_view.py`

```python
class PhotoMapView(QWidget):
    def __init__(self, ...):
        # ... 现有代码 ...
        self._person_filter: PersonMapFilter | None = None  # 🆕
        self._person_panel: PersonMapPanel | None = None     # 🆕

    def set_person_filter(self, filter: PersonMapFilter) -> None:
        self._person_filter = filter

    def set_person_panel(self, panel: PersonMapPanel) -> None:
        self._person_panel = panel
        panel.personSelected.connect(self._on_person_selected)
        panel.personDeselected.connect(self._on_person_deselected)

    @Slot(str)
    def _on_person_selected(self, person_id: str) -> None:
        """选中某人物，过滤地图标记"""
        if self._person_filter:
            filtered = self._person_filter.filter_by_person(person_id)
            self._marker_controller.set_assets(filtered, self._library_root)
            # 同时显示该人物轨迹
            if self._trail_service:
                trail = self._trail_service.build_trail()
                # 过滤轨迹点
                person_ids = {a.asset_id for a in filtered}
                filtered_segments = []
                for seg in trail.segments:
                    pts = [p for p in seg.points if p.asset_id in person_ids]
                    if pts:
                        filtered_segments.append(TrailSegment(
                            points=pts, start_time=pts[0].timestamp,
                            end_time=pts[-1].timestamp, color=seg.color
                        ))
                self._trail_layer.set_trail(TrailData(
                    segments=filtered_segments,
                    total_photos=sum(len(s.points) for s in filtered_segments),
                    date_range=trail.date_range,
                ))

    @Slot()
    def _on_person_deselected(self) -> None:
        """取消人物选择，显示全部"""
        if self._person_filter:
            all_assets = self._person_filter.filter_by_person(None)
            self._marker_controller.set_assets(all_assets, self._library_root)
            self._trail_layer.set_trail(TrailData(segments=[], total_photos=0,
                                                   date_range=(datetime.now(), datetime.now())))
```

### 3.5 实现步骤

| 步骤 | 任务 | 预计时间 | 依赖 |
|------|------|----------|------|
| 1 | 创建 `application/dtos.py` - PersonLocation, PersonMapSummary | 0.5d | 无 |
| 2 | 创建 `application/services/person_map_filter.py` - 过滤服务 | 1d | 步骤 1 |
| 3 | 创建 `gui/ui/widgets/person_map_panel.py` - 人物选择面板 | 1.5d | 步骤 1 |
| 4 | 修改 `photo_map_view.py` - 集成人物过滤 | 1d | 步骤 2, 3 |
| 5 | 人脸缩略图标记绘制（在标记上显示人脸） | 0.5d | 步骤 4 |
| 6 | 测试：单元测试 + UI 交互测试 | 0.5d | 步骤 1-5 |
| **合计** | | **~5 天** | |

---

## 4. 开发顺序与里程碑

```
┌─────────────────────────────────────────────────────────────┐
│                    开发路线图                                 │
│                                                             │
│  v6.2.0 - OCR 文字搜索（第 1-7 天）                          │
│  ─────────────────────────────────────────────────────      │
│  Day 1:   依赖添加 + OCR 引擎封装                            │
│  Day 2:   ocr_index.db + FTS5 仓储                          │
│  Day 3:   OCR Worker + 扫描集成                              │
│  Day 4:   搜索服务集成                                       │
│  Day 5:   搜索结果 UI                                        │
│  Day 6-7: 测试 + 修复                                        │
│                                                             │
│  v6.2.1 - 地图时间线/轨迹（第 8-14 天）                      │
│  ─────────────────────────────────────────────────────      │
│  Day 8:   数据模型 + 轨迹服务                                 │
│  Day 9:   轨迹绘制层                                         │
│  Day 10:  时间滑块控件                                       │
│  Day 11:  PhotoMapView 集成                                  │
│  Day 12:  视口裁剪优化                                       │
│  Day 13-14: 测试 + 修复                                      │
│                                                             │
│  v6.2.2 - 人脸+地图联动（第 15-19 天）                       │
│  ─────────────────────────────────────────────────────      │
│  Day 15:  过滤服务 + 数据模型                                 │
│  Day 16:  人物选择面板                                       │
│  Day 17:  PhotoMapView 集成                                  │
│  Day 18:  人脸缩略图标记                                     │
│  Day 19:  测试 + 修复                                        │
│                                                             │
│  v6.3.0 - 集成测试 + 发布（第 20-21 天）                     │
│  ─────────────────────────────────────────────────────      │
│  Day 20:  全量回归测试                                        │
│  Day 21:  文档更新 + 发布                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 依赖变更汇总

### `pyproject.toml` 新增

```toml
[project.optional-dependencies]
ai = [
    "onnxruntime>=1.17.0,<2",
    "rapidocr-onnxruntime>=1.3.0,<2",
    "huggingface-hub>=0.20.0,<1",
]
```

### 系统依赖

| 依赖 | 版本 | 说明 |
|------|------|------|
| SQLite | 3.35+ | FTS5 支持（Python 3.12 内置满足） |
| ONNX Runtime | 1.17+ | CPU 推理（pip 安装） |
| RapidOCR | 1.3+ | OCR 引擎（pip 安装） |

---

## 6. 风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| OCR 模型首次加载慢（~10s） | 用户体验 | 惰性加载 + 启动时后台预热 |
| OCR 识别中文准确率 | 搜索质量 | PP-OCRv5 中文优化版，可调置信度阈值 |
| 万级轨迹点性能 | 地图流畅度 | 视口裁剪 + 轨迹简化（Douglas-Peucker） |
| 人脸数据库并发 | 数据一致性 | 现有 FaceRepository 已有线程安全机制 |
| AI 模型体积（~500MB） | 安装包大小 | 首次使用时按需下载，不打包到安装包 |

---

> **文档维护者**：请在实现过程中更新本文档的"状态"列，标记每一步的完成情况。
