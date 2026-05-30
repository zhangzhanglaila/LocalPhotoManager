"""Repository for storing and retrieving image embeddings.

This module provides a separate SQLite database for storing CLIP embeddings,
keeping them independent from the main asset index for clean separation.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np

from ...utils.logging import get_logger
from ...utils.pathutils import ensure_work_dir

logger = get_logger()

# Database filename for embeddings
EMBEDDING_DB_NAME = "embeddings.db"

# Global singleton instance and lock
_global_instance: Optional["EmbeddingRepository"] = None
_global_lock = threading.Lock()


def get_embedding_repository(library_root: Path) -> "EmbeddingRepository":
    """Get or create the global EmbeddingRepository singleton.

    Parameters
    ----------
    library_root : Path
        The root directory of the library.

    Returns
    -------
    EmbeddingRepository
        The singleton EmbeddingRepository instance.
    """
    global _global_instance

    with _global_lock:
        resolved_root = library_root.resolve()

        if _global_instance is not None:
            if _global_instance.library_root.resolve() == resolved_root:
                return _global_instance
            _global_instance.close()

        _global_instance = EmbeddingRepository(resolved_root)
        return _global_instance


def reset_embedding_repository() -> None:
    """Reset the global repository singleton (for testing)."""
    global _global_instance

    with _global_lock:
        if _global_instance is not None:
            _global_instance.close()
            _global_instance = None


class EmbeddingRepository:
    """Repository for storing and retrieving image embeddings.

    This class manages a separate SQLite database for storing CLIP embeddings.
    Each embedding is associated with an asset ID and stored as a binary blob.
    """

    def __init__(self, library_root: Path):
        """Initialize the embedding repository.

        Parameters
        ----------
        library_root : Path
            The root directory of the library. The database will be created at
            `<library_root>/.iPhoto/embeddings.db`.
        """
        self.library_root = library_root
        self.path = ensure_work_dir(library_root) / EMBEDDING_DB_NAME
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.path), timeout=10.0)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        conn = self._get_conn()

        # Embeddings table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                asset_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                dimension INTEGER NOT NULL,
                model_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_asset_id
            ON embeddings(asset_id)
        """)

        # Captions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS captions (
                asset_id TEXT PRIMARY KEY,
                caption TEXT NOT NULL,
                language TEXT DEFAULT 'en',
                confidence REAL DEFAULT 1.0,
                model_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_captions_asset_id
            ON captions(asset_id)
        """)

        # Tags table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                tag_name TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(asset_id, tag_name)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags_asset_id
            ON tags(asset_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags_tag_name
            ON tags(tag_name)
        """)

        conn.commit()

    def store_embedding(
        self,
        asset_id: str,
        embedding: np.ndarray,
        model_name: Optional[str] = None,
    ) -> None:
        """Store an embedding for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.
        embedding : np.ndarray
            The embedding vector (float32).
        model_name : Optional[str]
            Name of the model used to generate the embedding.
        """
        conn = self._get_conn()

        # Convert numpy array to bytes
        embedding_bytes = embedding.astype(np.float32).tobytes()

        conn.execute(
            """
            INSERT OR REPLACE INTO embeddings (asset_id, embedding, dimension, model_name)
            VALUES (?, ?, ?, ?)
            """,
            (asset_id, embedding_bytes, len(embedding), model_name),
        )
        conn.commit()

    def store_embeddings_batch(
        self,
        embeddings: List[tuple[str, np.ndarray, Optional[str]]],
    ) -> None:
        """Store multiple embeddings in a batch.

        Parameters
        ----------
        embeddings : List[tuple]
            List of (asset_id, embedding, model_name) tuples.
        """
        conn = self._get_conn()

        data = []
        for asset_id, embedding, model_name in embeddings:
            embedding_bytes = embedding.astype(np.float32).tobytes()
            data.append((asset_id, embedding_bytes, len(embedding), model_name))

        conn.executemany(
            """
            INSERT OR REPLACE INTO embeddings (asset_id, embedding, dimension, model_name)
            VALUES (?, ?, ?, ?)
            """,
            data,
        )
        conn.commit()

    def get_embedding(self, asset_id: str) -> Optional[np.ndarray]:
        """Get the embedding for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.

        Returns
        -------
        Optional[np.ndarray]
            The embedding vector, or None if not found.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT embedding, dimension FROM embeddings WHERE asset_id = ?",
            (asset_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        embedding_bytes, dimension = row
        return np.frombuffer(embedding_bytes, dtype=np.float32).copy()

    def get_all_embeddings(self) -> List[dict]:
        """Get all stored embeddings.

        Returns
        -------
        List[dict]
            List of dicts with 'asset_id' and 'embedding' keys.
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT asset_id, embedding, dimension FROM embeddings")

        results = []
        for row in cursor:
            asset_id, embedding_bytes, dimension = row
            embedding = np.frombuffer(embedding_bytes, dtype=np.float32).copy()
            results.append({
                "asset_id": asset_id,
                "embedding": embedding,
            })

        return results

    def get_embeddings_by_ids(self, asset_ids: List[str]) -> List[dict]:
        """Get embeddings for specific assets.

        Parameters
        ----------
        asset_ids : List[str]
            List of asset identifiers.

        Returns
        -------
        List[dict]
            List of dicts with 'asset_id' and 'embedding' keys.
        """
        if not asset_ids:
            return []

        conn = self._get_conn()

        # Split into chunks to avoid SQLite parameter limit
        chunk_size = 900
        results = []

        for i in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cursor = conn.execute(
                f"SELECT asset_id, embedding, dimension FROM embeddings WHERE asset_id IN ({placeholders})",
                chunk,
            )

            for row in cursor:
                asset_id, embedding_bytes, dimension = row
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32).copy()
                results.append({
                    "asset_id": asset_id,
                    "embedding": embedding,
                })

        return results

    def delete_embedding(self, asset_id: str) -> None:
        """Delete the embedding for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.
        """
        conn = self._get_conn()
        conn.execute("DELETE FROM embeddings WHERE asset_id = ?", (asset_id,))
        conn.commit()

    def delete_embeddings_batch(self, asset_ids: List[str]) -> None:
        """Delete multiple embeddings in a batch.

        Parameters
        ----------
        asset_ids : List[str]
            List of asset identifiers.
        """
        if not asset_ids:
            return

        conn = self._get_conn()

        chunk_size = 900
        for i in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            conn.execute(
                f"DELETE FROM embeddings WHERE asset_id IN ({placeholders})",
                chunk,
            )
        conn.commit()

    def count(self) -> int:
        """Return the number of stored embeddings."""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM embeddings")
        return cursor.fetchone()[0]

    def has_embedding(self, asset_id: str) -> bool:
        """Check if an embedding exists for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.

        Returns
        -------
        bool
            True if an embedding exists.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT 1 FROM embeddings WHERE asset_id = ? LIMIT 1",
            (asset_id,),
        )
        return cursor.fetchone() is not None

    def get_asset_ids_without_embeddings(self, asset_ids: List[str]) -> List[str]:
        """Get asset IDs that don't have embeddings yet.

        Parameters
        ----------
        asset_ids : List[str]
            List of asset identifiers to check.

        Returns
        -------
        List[str]
            List of asset IDs without embeddings.
        """
        if not asset_ids:
            return []

        conn = self._get_conn()
        existing = set()

        chunk_size = 900
        for i in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cursor = conn.execute(
                f"SELECT asset_id FROM embeddings WHERE asset_id IN ({placeholders})",
                chunk,
            )
            existing.update(row[0] for row in cursor)

        return [aid for aid in asset_ids if aid not in existing]

    # Caption methods

    def store_caption(
        self,
        asset_id: str,
        caption: str,
        language: str = "en",
        confidence: float = 1.0,
        model_name: Optional[str] = None,
    ) -> None:
        """Store a caption for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.
        caption : str
            The caption text.
        language : str
            Language of the caption.
        confidence : float
            Confidence score.
        model_name : Optional[str]
            Name of the model used.
        """
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO captions (asset_id, caption, language, confidence, model_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (asset_id, caption, language, confidence, model_name),
        )
        conn.commit()

    def get_caption(self, asset_id: str) -> Optional[str]:
        """Get the caption for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.

        Returns
        -------
        Optional[str]
            The caption text, or None if not found.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT caption FROM captions WHERE asset_id = ?",
            (asset_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def get_captions_batch(self, asset_ids: List[str]) -> dict[str, str]:
        """Get captions for multiple assets.

        Parameters
        ----------
        asset_ids : List[str]
            List of asset identifiers.

        Returns
        -------
        dict[str, str]
            Dictionary mapping asset_id to caption.
        """
        if not asset_ids:
            return {}

        conn = self._get_conn()
        result = {}

        chunk_size = 900
        for i in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cursor = conn.execute(
                f"SELECT asset_id, caption FROM captions WHERE asset_id IN ({placeholders})",
                chunk,
            )
            result.update(dict(cursor))

        return result

    # Tag methods

    def store_tags(
        self,
        asset_id: str,
        tags: List[dict],
    ) -> None:
        """Store tags for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.
        tags : List[dict]
            List of tag dictionaries with 'name', 'category', and 'confidence'.
        """
        conn = self._get_conn()

        # Delete existing tags for this asset
        conn.execute("DELETE FROM tags WHERE asset_id = ?", (asset_id,))

        # Insert new tags
        for tag in tags:
            conn.execute(
                """
                INSERT INTO tags (asset_id, tag_name, category, confidence)
                VALUES (?, ?, ?, ?)
                """,
                (asset_id, tag["name"], tag.get("category", "general"), tag.get("confidence", 1.0)),
            )
        conn.commit()

    def get_tags(self, asset_id: str) -> List[dict]:
        """Get tags for an asset.

        Parameters
        ----------
        asset_id : str
            The asset identifier.

        Returns
        -------
        List[dict]
            List of tag dictionaries.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT tag_name, category, confidence FROM tags WHERE asset_id = ?",
            (asset_id,),
        )
        return [
            {"name": row[0], "category": row[1], "confidence": row[2]}
            for row in cursor
        ]

    def get_tags_batch(self, asset_ids: List[str]) -> dict[str, List[dict]]:
        """Get tags for multiple assets.

        Parameters
        ----------
        asset_ids : List[str]
            List of asset identifiers.

        Returns
        -------
        dict[str, List[dict]]
            Dictionary mapping asset_id to list of tags.
        """
        if not asset_ids:
            return {}

        conn = self._get_conn()
        result: dict[str, List[dict]] = {aid: [] for aid in asset_ids}

        chunk_size = 900
        for i in range(0, len(asset_ids), chunk_size):
            chunk = asset_ids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            cursor = conn.execute(
                f"SELECT asset_id, tag_name, category, confidence FROM tags WHERE asset_id IN ({placeholders})",
                chunk,
            )
            for row in cursor:
                asset_id, tag_name, category, confidence = row
                if asset_id not in result:
                    result[asset_id] = []
                result[asset_id].append({
                    "name": tag_name,
                    "category": category,
                    "confidence": confidence,
                })

        return result

    def search_by_tag(self, tag_name: str) -> List[str]:
        """Search for assets by tag name.

        Parameters
        ----------
        tag_name : str
            The tag name to search for.

        Returns
        -------
        List[str]
            List of asset IDs with the tag.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT DISTINCT asset_id FROM tags WHERE tag_name = ?",
            (tag_name,),
        )
        return [row[0] for row in cursor]

    def get_all_tags(self) -> List[dict]:
        """Get all unique tags with their counts.

        Returns
        -------
        List[dict]
            List of dictionaries with 'name', 'category', and 'count'.
        """
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT tag_name, category, COUNT(*) as count
            FROM tags
            GROUP BY tag_name, category
            ORDER BY count DESC
        """)
        return [
            {"name": row[0], "category": row[1], "count": row[2]}
            for row in cursor
        ]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
