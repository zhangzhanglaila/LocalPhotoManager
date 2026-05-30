"""Library-scoped runtime session for vNext application boundaries."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..application.ports import (
    AssetRepositoryPort,
    AssetStateServicePort,
    EditServicePort,
    LibraryStateRepositoryPort,
    LocationAssetServicePort,
    MapInteractionServicePort,
    MapRuntimePort,
)
from ..application.services.map_interaction_service import LibraryMapInteractionService
from ..infrastructure.repositories.library_state_repository import (
    IndexStoreLibraryStateRepository,
)
from ..infrastructure.services.library_asset_runtime import LibraryAssetRuntime
from ..infrastructure.services.location_metadata_service import (
    ExifToolLocationMetadataService,
)
from ..infrastructure.services.map_runtime_service import SessionMapRuntimeService
from ..application.services.assign_location_service import AssignLocationService
from ..people.service import PeopleService
from .library_asset_state_service import LibraryAssetStateService
from .library_album_metadata_service import LibraryAlbumMetadataService
from .library_asset_lifecycle_service import LibraryAssetLifecycleService
from .library_asset_operation_service import LibraryAssetOperationService
from .library_asset_query_service import LibraryAssetQueryService
from .library_edit_service import LibraryEditService
from .library_location_service import LibraryLocationService
from .library_people_service import create_people_service
from .library_scan_service import LibraryScanService

logger = logging.getLogger(__name__)


@dataclass
class LibrarySession:
    """Own library-scoped adapters and expose the application-facing surface."""

    library_root: Path
    asset_runtime: LibraryAssetRuntime | None = None
    state_repository: LibraryStateRepositoryPort | None = None
    asset_state: AssetStateServicePort | None = None
    album_metadata: LibraryAlbumMetadataService | None = None
    asset_queries: LibraryAssetQueryService | None = None
    scans: LibraryScanService | None = None
    asset_lifecycle: LibraryAssetLifecycleService | None = None
    asset_operations: LibraryAssetOperationService | None = None
    people: PeopleService | None = None
    maps: MapRuntimePort | None = None
    map_interactions: MapInteractionServicePort | None = None
    edit: EditServicePort | None = None
    locations: LocationAssetServicePort | None = None
    bind_asset_runtime: bool = True
    # Agent services (optional, initialized lazily)
    _search_service: object = field(default=None, repr=False)
    _embedding_service: object = field(default=None, repr=False)
    _embedding_repository: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.library_root = Path(self.library_root)
        if self.asset_runtime is None:
            self.asset_runtime = LibraryAssetRuntime(self.library_root)
            self.bind_asset_runtime = False
        if self.bind_asset_runtime:
            self.asset_runtime.bind_library_root(self.library_root)
        if self.state_repository is None:
            self.state_repository = IndexStoreLibraryStateRepository(self.library_root)
        if self.asset_queries is None:
            self.asset_queries = LibraryAssetQueryService(self.library_root)
        if self.asset_state is None:
            self.asset_state = LibraryAssetStateService(
                self.library_root,
                state_repository=self.state_repository,
                favorite_query=self.asset_queries,
            )
        if self.album_metadata is None:
            self.album_metadata = LibraryAlbumMetadataService(
                self.library_root,
                state_repository=self.state_repository,
            )
        if self.scans is None:
            self.scans = LibraryScanService(self.library_root)
        if self.asset_lifecycle is None:
            self.asset_lifecycle = LibraryAssetLifecycleService(
                self.library_root,
                scan_service=self.scans,
            )
        if self.asset_operations is None:
            self.asset_operations = LibraryAssetOperationService(
                self.library_root,
                lifecycle_service=self.asset_lifecycle,
            )
        if self.people is None:
            self.people = create_people_service(self.library_root)
        if self.maps is None:
            self.maps = SessionMapRuntimeService()
        if self.map_interactions is None:
            self.map_interactions = LibraryMapInteractionService()
        if self.edit is None:
            self.edit = LibraryEditService(self.library_root)
        if self.locations is None:
            self.locations = LibraryLocationService(
                self.library_root,
                query_service=self.asset_queries,
            )
        bind_edit_service = getattr(self.asset_runtime, "bind_edit_service", None)
        if callable(bind_edit_service):
            bind_edit_service(self.edit)

    def get_search_service(self):
        """Get or initialize the semantic search service.

        Returns
        -------
        SearchService or None
            The search service, or None if agent dependencies are not installed.
        """
        if self._search_service is not None:
            return self._search_service

        try:
            from ..agent.services.search_service import SearchService
            from ..agent.infrastructure.clip_embedding import CLIPEmbeddingService
            from ..cache.index_store.embedding_repository import get_embedding_repository

            # Initialize embedding service
            model_dir = self.library_root.parent / "extension" / "models"
            if not model_dir.exists():
                model_dir = Path("src/extension/models")

            embedding_service = CLIPEmbeddingService(model_dir=model_dir)
            if not embedding_service.is_loaded():
                logger.warning("CLIP model not available. Semantic search disabled.")
                # Show dialog to user
                self._show_model_download_dialog(model_dir)
                return None

            # Get embedding repository
            embedding_repo = get_embedding_repository(self.library_root)

            # Create search service
            self._search_service = SearchService(
                embedding_service=embedding_service,
                asset_repository=self.asset_runtime.assets,
                embedding_repository=embedding_repo,
            )
            self._embedding_service = embedding_service
            self._embedding_repository = embedding_repo

            return self._search_service

        except ImportError as e:
            logger.debug("Agent dependencies not installed: %s", e)
            return None
        except Exception as e:
            logger.warning("Failed to initialize search service: %s", e)
            return None

    def _show_model_download_dialog(self, model_dir: Path) -> None:
        """Show dialog to user about missing CLIP model.

        Parameters
        ----------
        model_dir : Path
            Expected model directory.
        """
        try:
            from PySide6.QtWidgets import QMessageBox, QPushButton

            msg = QMessageBox()
            msg.setWindowTitle("语义搜索需要下载模型")
            msg.setText(
                "语义搜索功能需要下载 CLIP 模型（约 350MB）。\n\n"
                f"模型目录: {model_dir}\n\n"
                "是否现在下载？"
            )
            msg.setInformativeText(
                "下载后可以使用以下功能：\n"
                "• 语义搜索（如搜索"黄鹤楼"、"海边"等）\n"
                "• 以图搜图\n"
                "• 查找重复照片\n"
                "• 智能相册创建"
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)

            result = msg.exec()

            if result == QMessageBox.StandardButton.Yes:
                self._download_model(model_dir)

        except Exception as e:
            logger.error("Failed to show download dialog: %s", e)

    def _download_model(self, model_dir: Path) -> None:
        """Download CLIP model in background.

        Parameters
        ----------
        model_dir : Path
            Directory to save the model.
        """
        try:
            from PySide6.QtCore import QRunnable, Slot, QThreadPool, Signal, QObject
            from PySide6.QtWidgets import QProgressDialog
            from ..agent.infrastructure.clip_downloader import download_model_with_transformers

            # Create progress dialog
            progress = QProgressDialog("正在下载 CLIP 模型...", "取消", 0, 100)
            progress.setWindowTitle("下载模型")
            progress.setMinimumDuration(0)
            progress.setValue(0)

            class DownloadWorker(QRunnable):
                def __init__(self, callback):
                    super().__init__()
                    self.setAutoDelete(True)
                    self._callback = callback

                @Slot()
                def run(self):
                    def progress_callback(current, total, message):
                        self._callback(current, total, message)

                    success = download_model_with_transformers(
                        model_dir=model_dir,
                        progress_callback=progress_callback,
                    )
                    self._callback(100, 100, "下载完成！" if success else "下载失败")

            def on_progress(current, total, message):
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: progress.setValue(current))
                QTimer.singleShot(0, lambda: progress.setLabelText(message))

            worker = DownloadWorker(on_progress)
            QThreadPool.globalInstance().start(worker)

            progress.exec()

        except Exception as e:
            logger.error("Failed to download model: %s", e)

    def get_embedding_repository(self):
        """Get or initialize the embedding repository.

        Returns
        -------
        EmbeddingRepository or None
            The embedding repository, or None if initialization fails.
        """
        if self._embedding_repository is not None:
            return self._embedding_repository

        try:
            from ..cache.index_store.embedding_repository import get_embedding_repository
            self._embedding_repository = get_embedding_repository(self.library_root)
            return self._embedding_repository
        except Exception as e:
            logger.warning("Failed to initialize embedding repository: %s", e)
            return None

    def get_embedding_service(self):
        """Get or initialize the embedding service.

        Returns
        -------
        CLIPEmbeddingService or None
            The embedding service, or None if not available.
        """
        if self._embedding_service is not None:
            return self._embedding_service

        try:
            from ..agent.infrastructure.clip_embedding import CLIPEmbeddingService

            model_dir = self.library_root.parent / "extension" / "models"
            if not model_dir.exists():
                model_dir = Path("src/extension/models")

            self._embedding_service = CLIPEmbeddingService(model_dir=model_dir)
            return self._embedding_service
        except Exception as e:
            logger.warning("Failed to initialize embedding service: %s", e)
            return None

    @property
    def assets(self) -> AssetRepositoryPort:
        return self.asset_runtime.assets

    @property
    def thumbnails(self):
        return self.asset_runtime.thumbnail_service

    @property
    def state(self) -> LibraryStateRepositoryPort:
        assert self.state_repository is not None
        return self.state_repository

    def assign_location_service(self) -> AssignLocationService:
        return AssignLocationService(self.state, ExifToolLocationMetadataService())

    def shutdown(self) -> None:
        bind_edit_service = getattr(self.asset_runtime, "bind_edit_service", None)
        if callable(bind_edit_service):
            bind_edit_service(None)
        self.asset_runtime.shutdown()


def create_headless_library_session(root: Path) -> LibrarySession:
    """Create a library session for non-GUI entry points such as the CLI."""

    library_root = Path(root)
    return LibrarySession(
        library_root,
        asset_runtime=LibraryAssetRuntime(library_root),
        bind_asset_runtime=False,
    )


def create_library_state_repository(root: Path) -> LibraryStateRepositoryPort:
    """Create the current state adapter for compatibility entry points."""

    return IndexStoreLibraryStateRepository(Path(root))


__all__ = [
    "LibrarySession",
    "create_headless_library_session",
    "create_library_state_repository",
]
