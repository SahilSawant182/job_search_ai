# -*- coding: utf-8 -*-
# job_search_ai/services/ai/vector_index.py
#
# VectorIndex
# -----------
# Abstraction layer over the vector database.  Today backed by Qdrant;
# tomorrow any other vector DB can be substituted here without touching
# any business logic or agent code.
#
# Responsibility
# --------------
#   Raw vector operations ONLY:
#     health, create_collection, upsert, delete, search, collection_info
#
# NOT responsible for:
#   - Generating embeddings (that is EmbeddingService)
#   - Business objects (Career Knowledge, Student, …)
#   - Prompt construction or LLM calls
#
# Configuration
# -------------
#   All parameters read from SettingsService:
#     qdrant_url             — Qdrant server base URL
#     qdrant_collection_name — default collection
#     embedding_dimension    — vector dimensionality
#     vector_distance        — similarity metric (Cosine | Dot | Euclid)
#
# Qdrant client version
# ---------------------
#   qdrant-client 1.18.0  (already installed in bench virtualenv)

from __future__ import annotations

import logging
import time
from typing import Any, TYPE_CHECKING

from qdrant_client import QdrantClient
from qdrant_client.models import (
    CollectionStatus,
    Distance,
    PointIdsList,
    PointStruct,
    VectorParams,
)

if TYPE_CHECKING:
    from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class VectorIndexError(Exception):
    """Raised by VectorIndex for any vector-database operation failure.

    Wraps Qdrant client errors, connection problems, and configuration
    issues into a single predictable exception type for callers.
    """


# ---------------------------------------------------------------------------
# Return type for search results
# ---------------------------------------------------------------------------

class SearchResult:
    """A single result returned by VectorIndex.search().

    Business logic must NOT be placed here.  This is a plain data
    carrier — no deserialization of Career Knowledge or any DocType.

    Attributes
    ----------
    id      : str | int   — the vector point ID (matches the MariaDB document name)
    score   : float       — similarity score (higher = more similar for Cosine)
    payload : dict        — raw metadata stored alongside the vector
    """

    __slots__ = ("id", "score", "payload")

    def __init__(self, id: "str | int", score: float, payload: "dict[str, Any]") -> None:
        self.id      = id
        self.score   = score
        self.payload = payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"SearchResult(id={self.id!r}, score={self.score:.4f}, payload={self.payload})"


# ---------------------------------------------------------------------------
# VectorIndex
# ---------------------------------------------------------------------------

class VectorIndex:
    """Abstraction layer over the vector database (currently Qdrant).

    All methods operate on raw vectors and primitive types.  No business
    objects are created or returned.

    Public API
    ----------
    ::

        vi = VectorIndex()

        # ensure collection exists
        vi.create_collection()

        # insert / update a vector
        vi.upsert(id="CK-00001", vector=[0.1, 0.2, …], payload={"career": "ML"})

        # semantic search
        results = vi.search(query_vector=[…], limit=5)

        # remove a vector
        vi.delete(id="CK-00001")

        # introspect the collection
        info = vi.collection_info()

        # verify connectivity
        status = vi.health()

    Parameters
    ----------
    settings : SettingsService | None
        Optional override for unit tests.  Defaults to the global singleton.
    """

    # Map config strings → qdrant Distance enum
    _DISTANCE_MAP: dict[str, Distance] = {
        "Cosine": Distance.COSINE,
        "Dot":    Distance.DOT,
        "Euclid": Distance.EUCLID,
    }

    def __init__(self, settings: "SettingsService | None" = None) -> None:
        if settings is None:
            from job_search_ai.services.settings_service import SettingsService
            settings = SettingsService.get()

        self._settings = settings
        self._client: QdrantClient | None = None

    # ------------------------------------------------------------------
    # Lazy client accessor
    # ------------------------------------------------------------------

    def _get_client(self) -> QdrantClient:
        """Return (and lazily create) the Qdrant client."""
        if self._client is None:
            url = self._settings.qdrant_url
            try:
                self._client = QdrantClient(url=url, timeout=30)
            except Exception as exc:
                raise VectorIndexError(
                    f"VectorIndex: failed to create Qdrant client for {url!r} — {exc}"
                ) from exc
        return self._client

    def _collection(self) -> str:
        """Return the configured collection name."""
        return self._settings.qdrant_collection_name

    def _distance(self) -> Distance:
        """Map the configured distance string to a Qdrant Distance enum."""
        metric = self._settings.vector_distance
        dist = self._DISTANCE_MAP.get(metric)
        if dist is None:
            raise VectorIndexError(
                f"VectorIndex: unsupported distance metric {metric!r}. "
                f"Valid values: {list(self._DISTANCE_MAP)}"
            )
        return dist

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Check Qdrant connectivity and return status information.

        Returns
        -------
        dict with keys:
            status       — "ok" or "error"
            qdrant_url   — the configured server URL
            collections  — list of collection names visible on the server
            message      — human-readable status line

        Raises
        ------
        VectorIndexError
            If the server is unreachable.
        """
        t_start = time.perf_counter()
        logger.info("VectorIndex.health: checking connectivity to %s", self._settings.qdrant_url)
        try:
            client = self._get_client()
            col_response = client.get_collections()
            collections = [c.name for c in col_response.collections]
            elapsed = time.perf_counter() - t_start
            logger.info("VectorIndex.health: OK — %d collection(s) found in %.3fs", len(collections), elapsed)
            return {
                "status": "ok",
                "qdrant_url": self._settings.qdrant_url,
                "collections": collections,
                "message": f"Qdrant reachable. {len(collections)} collection(s) found.",
            }
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(
                f"VectorIndex.health: cannot reach Qdrant at {self._settings.qdrant_url!r} — {exc}"
            ) from exc

    def create_collection(self, *, recreate: bool = False) -> bool:
        """Create the configured collection if it does not already exist.

        Parameters
        ----------
        recreate : bool
            If *True*, drop and re-create the collection even if it exists.
            Use with caution — this deletes all vectors.

        Returns
        -------
        bool
            *True* if the collection was created, *False* if it already
            existed and ``recreate=False``.

        Raises
        ------
        VectorIndexError
            On Qdrant communication errors.
        """
        collection = self._collection()
        dimension  = self._settings.embedding_dimension
        distance   = self._distance()

        t_start = time.perf_counter()
        logger.info(
            "VectorIndex.create_collection: collection=%r  dim=%d  distance=%s  recreate=%s",
            collection, dimension, distance.value, recreate,
        )

        try:
            client = self._get_client()

            if recreate:
                client.recreate_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=dimension, distance=distance),
                )
                elapsed = time.perf_counter() - t_start
                logger.info("VectorIndex.create_collection: recreated %r in %.3fs", collection, elapsed)
                return True

            # Check existence first to avoid overwriting data accidentally
            existing = {c.name for c in client.get_collections().collections}
            if collection in existing:
                logger.info("VectorIndex.create_collection: %r already exists, skipping", collection)
                return False

            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dimension, distance=distance),
            )
            elapsed = time.perf_counter() - t_start
            logger.info("VectorIndex.create_collection: created %r in %.3fs", collection, elapsed)
            return True

        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(
                f"VectorIndex.create_collection: failed for collection {collection!r} — {exc}"
            ) from exc

    def upsert(
        self,
        id: str | int,
        vector: list[float],
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update a single vector point.

        Parameters
        ----------
        id : str | int
            Unique identifier for this vector point.  Use the MariaDB
            document name (e.g. "CK-00001") as the string ID.
        vector : list[float]
            The dense embedding vector.  Must match ``embedding_dimension``.
        payload : dict | None
            Arbitrary key-value metadata stored alongside the vector.
            Keep lightweight — do NOT store the full document here.
            MariaDB is the source of truth.

        Raises
        ------
        VectorIndexError
            On validation failures or Qdrant errors.
        """
        self._validate_vector(vector)
        collection = self._collection()
        payload = dict(payload) if payload else {}

        # Resolve the caller-supplied id to a Qdrant-compatible UUID.
        # The original string is preserved in the payload as "doc_id" so
        # search results can surface it without touching the raw UUID.
        qdrant_id = self._resolve_id(id)
        payload.setdefault("doc_id", str(id))

        t_start = time.perf_counter()
        logger.info(
            "VectorIndex.upsert: id=%r  qdrant_id=%s  dims=%d  payload_keys=%s  collection=%r",
            id, qdrant_id, len(vector), list(payload.keys()), collection,
        )

        try:
            client = self._get_client()
            client.upsert(
                collection_name=collection,
                points=[PointStruct(id=qdrant_id, vector=vector, payload=payload)],
            )
            elapsed = time.perf_counter() - t_start
            logger.info("VectorIndex.upsert: id=%r completed in %.3fs", id, elapsed)
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(
                f"VectorIndex.upsert: failed for id={id!r} in collection {collection!r} — {exc}"
            ) from exc

    def delete(self, id: str | int) -> None:
        """Delete a vector point by its ID.

        Parameters
        ----------
        id : str | int
            The ID that was used when calling ``upsert()``.

        Raises
        ------
        VectorIndexError
            On Qdrant errors.  Does NOT raise if the ID does not exist.
        """
        collection = self._collection()
        qdrant_id = self._resolve_id(id)
        t_start = time.perf_counter()
        logger.info("VectorIndex.delete: id=%r  qdrant_id=%s  collection=%r", id, qdrant_id, collection)

        try:
            client = self._get_client()
            client.delete(
                collection_name=collection,
                points_selector=PointIdsList(points=[qdrant_id]),
            )
            elapsed = time.perf_counter() - t_start
            logger.info("VectorIndex.delete: id=%r completed in %.3fs", id, elapsed)
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(
                f"VectorIndex.delete: failed for id={id!r} in collection {collection!r} — {exc}"
            ) from exc

    def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        """Search for the nearest vectors to ``query_vector``.

        Parameters
        ----------
        query_vector : list[float]
            The dense query embedding.
        limit : int
            Maximum number of results to return.  Default: 10.
        score_threshold : float | None
            If provided, only results with score ≥ this value are returned.

        Returns
        -------
        list[SearchResult]
            Ranked by similarity score (highest first).  Each item carries
            the raw ``id``, ``score``, and ``payload`` dict.
            Business logic deserialization must be done by the caller.

        Raises
        ------
        VectorIndexError
            On Qdrant errors.
        """
        self._validate_vector(query_vector)
        collection = self._collection()

        t_start = time.perf_counter()
        logger.info(
            "VectorIndex.search: collection=%r  limit=%d  threshold=%s",
            collection, limit, score_threshold,
        )

        try:
            client = self._get_client()
            response = client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            hits = response.points
            elapsed = time.perf_counter() - t_start
            logger.info(
                "VectorIndex.search: found %d result(s) in %.3fs", len(hits), elapsed
            )
            return [
                SearchResult(
                    # Surface the original doc_id if stored in payload;
                    # fall back to the raw Qdrant UUID string.
                    id=h.payload.get("doc_id", str(h.id)) if h.payload else str(h.id),
                    score=h.score,
                    payload=h.payload or {},
                )
                for h in hits
            ]
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(
                f"VectorIndex.search: failed in collection {collection!r} — {exc}"
            ) from exc

    def collection_info(self) -> dict[str, Any]:
        """Return metadata about the configured collection.

        Returns
        -------
        dict with keys:
            name        — collection name
            status      — "green", "yellow", "red", or "unknown"
            vector_count — number of indexed vectors
            dimension   — vector dimensionality
            distance    — similarity metric name

        Raises
        ------
        VectorIndexError
            If the collection does not exist or Qdrant is unreachable.
        """
        collection = self._collection()
        t_start = time.perf_counter()
        logger.info("VectorIndex.collection_info: collection=%r", collection)

        try:
            client = self._get_client()
            info = client.get_collection(collection_name=collection)
            elapsed = time.perf_counter() - t_start

            status_map = {
                CollectionStatus.GREEN:  "green",
                CollectionStatus.YELLOW: "yellow",
                CollectionStatus.RED:    "red",
            }
            status_str = status_map.get(info.status, "unknown")

            result = {
                "name":         collection,
                "status":       status_str,
                "vector_count": info.points_count,
                "dimension":    info.config.params.vectors.size,
                "distance":     info.config.params.vectors.distance.value,
            }
            logger.info(
                "VectorIndex.collection_info: %r — vectors=%d  status=%s  elapsed=%.3fs",
                collection, info.points_count, status_str, elapsed,
            )
            return result
        except VectorIndexError:
            raise
        except Exception as exc:
            raise VectorIndexError(
                f"VectorIndex.collection_info: failed for collection {collection!r} — {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_vector(self, vector: list[float]) -> None:
        """Raise VectorIndexError if *vector* is malformed."""
        if not vector:
            raise VectorIndexError("VectorIndex: vector must be a non-empty list of floats.")
        if not isinstance(vector, list):
            raise VectorIndexError(
                f"VectorIndex: expected list[float], got {type(vector).__name__}."
            )
        if not all(isinstance(v, (int, float)) for v in vector):
            raise VectorIndexError("VectorIndex: vector must contain only numeric values.")

    @staticmethod
    def _resolve_id(id: "str | int") -> "str | int":
        """Convert *id* to a Qdrant-compatible point ID.

        Qdrant accepts only unsigned integers or UUIDs.  When *id* is an
        integer it is passed through unchanged.  When it is a string (e.g.
        a Frappe document name like "CK-00001"), a deterministic UUID v5
        is derived from it using the DNS namespace, giving a stable, unique
        UUID for each unique string.

        The original string is always stored in the payload under the key
        ``doc_id`` (handled by ``upsert``) so search results can recover
        the human-readable identifier.
        """
        import uuid
        if isinstance(id, int):
            return id
        # Try to parse as UUID first (callers may already pass a UUID string)
        try:
            return str(uuid.UUID(str(id)))
        except ValueError:
            pass
        # Derive a stable UUID5 from the string
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(id)))
