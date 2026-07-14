# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/knowledge_retriever.py
#
# KnowledgeRetriever
# ------------------
# Retrieves relevant Career Knowledge records for a given StudentProfile
# using semantic vector search.
#
# Pipeline
# --------
#
#   StudentProfile
#         │
#         ▼  _build_search_text()
#         │  "Computer Engineering student in India interested in React, JavaScript"
#         │
#         ▼  EmbeddingService.embed()
#         │  list[float]  (768-dim)
#         │
#         ▼  VectorIndex.search()
#         │  List[SearchResult]  with (id=doc_name, score, payload)
#         │
#         ▼  _load_from_mariadb()
#         │  frappe.get_doc("Career Knowledge", doc_name)  × N
#         │
#         ▼
#   List[RetrievedKnowledge]  ordered by similarity score (highest first)
#
# Rules
# -----
#   • ONLY retrieval — no Tavily, no LLM, no prompts, no recommendations
#   • MariaDB is the source of truth; Qdrant provides IDs only
#   • limit and score_threshold come from SettingsService (never hardcoded)
#   • No degree / branch / if-else skill filtering logic
#
# Configuration (from SettingsService)
# -------------------------------------
#   similarity_threshold     — float  (default 0.75)
#   max_retrieved_knowledge  — int    (default 5)

from __future__ import annotations

import logging
import time
from typing import Any, TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from job_search_ai.services.settings_service import SettingsService
    from job_search_ai.agents.career_trend.schemas import StudentProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class KnowledgeRetrieverError(Exception):
    """Raised by KnowledgeRetriever for any retrieval pipeline failure.

    Wraps embedding errors, Qdrant errors, and MariaDB fetch errors into a
    single predictable exception type for callers.
    """


# ---------------------------------------------------------------------------
# Result carrier
# ---------------------------------------------------------------------------

class RetrievedKnowledge:
    """A single Career Knowledge record returned by KnowledgeRetriever.

    Attributes
    ----------
    doc_name      : str   — Frappe document name (e.g. "CK-00001")
    similarity    : float — vector similarity score from Qdrant (0.0–1.0)
    career_name   : str
    industry      : str
    category      : str
    country       : str
    summary       : str
    future_demand : str
    career_stage  : str
    confidence    : float
    skills        : list[str]
    companies     : list[str]
    needs_refresh : bool  — True if expired or flagged for refresh
    """

    __slots__ = (
        "doc_name", "similarity", "hybrid_score",
        "career_name", "industry", "category", "country", "summary",
        "future_demand", "career_stage", "confidence",
        "skills", "companies", "needs_refresh",
    )

    def __init__(
        self,
        doc_name: str,
        similarity: float,
        hybrid_score: float,
        career_name: str,
        industry: str = "",
        category: str = "",
        country: str = "",
        summary: str = "",
        future_demand: str = "",
        career_stage: str = "",
        confidence: float = 0.0,
        skills: list[str] | None = None,
        companies: list[str] | None = None,
        needs_refresh: bool = False,
    ) -> None:
        self.doc_name      = doc_name
        self.similarity    = similarity
        self.hybrid_score  = hybrid_score
        self.career_name   = career_name
        self.industry      = industry
        self.category      = category
        self.country       = country
        self.summary       = summary
        self.future_demand = future_demand
        self.career_stage  = career_stage
        self.confidence    = confidence
        self.skills        = skills or []
        self.companies     = companies or []
        self.needs_refresh = needs_refresh


    def __repr__(self) -> str:
        return (
            f"RetrievedKnowledge(doc={self.doc_name!r}  "
            f"career={self.career_name!r}  similarity={self.similarity:.4f}  "
            f"hybrid_score={self.hybrid_score:.4f})"
        )


# ---------------------------------------------------------------------------
# KnowledgeRetriever
# ---------------------------------------------------------------------------

class KnowledgeRetriever:
    """Retrieve relevant Career Knowledge records for a StudentProfile.

    The retriever converts the student profile into a single semantic search
    text, generates its embedding, queries Qdrant for similar vectors, then
    loads the full Career Knowledge documents from MariaDB.

    It has NO responsibility for:
      - Searching the web (Tavily)
      - Calling LLMs
      - Building prompts
      - Recommending careers
      - Filtering by degree, branch, or skills

    Parameters
    ----------
    settings : SettingsService | None
        Optional override for testing. Defaults to the global singleton.
    embedding_service : EmbeddingService | None
        Optional override for testing. Defaults to a fresh EmbeddingService().
    vector_index : VectorIndex | None
        Optional override for testing. Defaults to a fresh VectorIndex().
    """

    def __init__(
        self,
        settings: "SettingsService | None" = None,
        embedding_service: Any | None = None,
        vector_index: Any | None = None,
    ) -> None:
        if settings is None:
            from job_search_ai.services.settings_service import SettingsService
            settings = SettingsService.get()
        self._settings = settings

        if embedding_service is None:
            from job_search_ai.services.ai.embedding_service import EmbeddingService
            embedding_service = EmbeddingService(settings=settings)
        self._embedding_svc = embedding_service

        if vector_index is None:
            from job_search_ai.services.ai.vector_index import VectorIndex
            vector_index = VectorIndex(settings=settings)
        self._vector_index = vector_index

    # ------------------------------------------------------------------
    # Public method
    # ------------------------------------------------------------------

    def retrieve(self, student: "StudentProfile") -> list[RetrievedKnowledge]:
        """Retrieve Career Knowledge records relevant to *student*.

        Parameters
        ----------
        student : StudentProfile
            The student profile from agents.career_trend.schemas.

        Returns
        -------
        list[RetrievedKnowledge]
            Ordered by similarity score (highest first).
            Empty list if no records meet the configured threshold.

        Raises
        ------
        KnowledgeRetrieverError
            On embedding failure, Qdrant error, or MariaDB fetch error.
        """
        timings: dict[str, float] = {}

        # Stage 1 — Build semantic search text
        search_text = self._build_search_text(student)
        logger.info(
            "KnowledgeRetriever: search_text=%r  threshold=%.2f  limit=%d",
            search_text,
            self._settings.similarity_threshold,
            self._settings.max_retrieved_knowledge,
        )

        # Stage 2 — Generate embedding
        t = time.perf_counter()
        vector = self._embed(search_text)
        timings["embedding"] = time.perf_counter() - t
        logger.info("KnowledgeRetriever: embedding done  dims=%d  elapsed=%.3fs", len(vector), timings["embedding"])

        # Stage 3 — Search the vector index
        t = time.perf_counter()
        vector_hits = self._search_vector_index(vector)
        timings["vector_search"] = time.perf_counter() - t
        logger.info(
            "KnowledgeRetriever: vector search done  hits=%d  elapsed=%.3fs",
            len(vector_hits), timings["vector_search"],
        )

        if not vector_hits:
            logger.info("KnowledgeRetriever: no vector results above threshold — returning empty list")
            return []     

        # Stage 4 — Load full records from MariaDB
        t = time.perf_counter()
        records = self._load_from_mariadb(vector_hits, student)
        timings["db_fetch"] = time.perf_counter() - t
        logger.info(
            "KnowledgeRetriever: MariaDB fetch done  loaded=%d  elapsed=%.3fs",
            len(records), timings["db_fetch"],
        )

        # Metrics
        avg_similarity = (
            sum(r.similarity for r in records) / len(records) if records else 0.0
        )
        total = sum(timings.values())
        logger.info(
            "KnowledgeRetriever: pipeline complete  "
            "retrieved=%d  avg_similarity=%.4f  total=%.3fs  stages=%s",
            len(records), avg_similarity, total,
            {k: f"{v:.3f}s" for k, v in timings.items()},
        )

        return records

    # ------------------------------------------------------------------
    # Stage 1 — Build search text
    # ------------------------------------------------------------------

    @staticmethod
    def _build_search_text(student: "StudentProfile") -> str:
        """Construct a career-centric semantic retrieval string from the student profile.

        The knowledge base stores careers (Frontend Developer, Data Engineer, etc.),
        NOT branches (Computer Engineering).  So the retrieval string must lead with
        career-focused signals: interests and skills.

        Format mirrors KnowledgeBuilder._build_embed_text for maximum cosine
        similarity matching:
            <career_focus> | <industry> | <skills> | <country>

        Priority of signals
        -------------------
        1. interests  — most explicit intent signal from student
        2. skills     — next best; reveals specialisation
        3. branch     — fallback; least specific for career matching
        """
        parts: list[str] = []

        # 1. Career focus from interests (most important signal)
        if student.interests:
            parts.append(", ".join(student.interests[:3]))

        # 2. Skills (high-value signal — directly match Career Knowledge skills)
        if student.skills:
            parts.append("skills: " + ", ".join(student.skills[:8]))

        # 3. Branch (fallback metadata)
        if student.branch:
            parts.append(student.branch)

        # 4. Country (for geo-filtered knowledge)
        if student.country:
            parts.append(student.country)

        return " | ".join(parts) if parts else student.branch

    # ------------------------------------------------------------------
    # Stage 2 — Embedding
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        """Embed *text* into a dense float vector."""
        try:
            return self._embedding_svc.embed(text)
        except Exception as exc:
            raise KnowledgeRetrieverError(
                f"KnowledgeRetriever: embedding failed for text={text!r} — {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Stage 3 — Vector search
    # ------------------------------------------------------------------

    def _search_vector_index(self, vector: list[float]) -> list:
        """Query Qdrant and return raw SearchResult objects.

        Uses limit and score_threshold from SettingsService.
        """
        try:
            return self._vector_index.search(
                query_vector    = vector,
                limit           = self._settings.max_retrieved_knowledge,
                score_threshold = self._settings.similarity_threshold,
            )
        except Exception as exc:
            raise KnowledgeRetrieverError(
                f"KnowledgeRetriever: vector search failed — {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Stage 4 — MariaDB fetch
    # ------------------------------------------------------------------

    def _load_from_mariadb(self, vector_hits: list, student: "StudentProfile") -> list[RetrievedKnowledge]:
        """Load full Career Knowledge documents from MariaDB and compute hybrid similarity.

        Qdrant provides the doc_name IDs and similarity scores.
        All business data comes from MariaDB.

        Parameters
        ----------
        vector_hits : list[SearchResult]
            Hits from VectorIndex.search(), each has .id, .score, .payload.
        student : StudentProfile
            The student profile used to calculate hybrid matching factors.

        Returns
        -------
        list[RetrievedKnowledge]
            Ordered by similarity score (highest first).
        """
        records: list[RetrievedKnowledge] = []

        for hit in vector_hits:
            # hit.id is the doc_name stored as doc_id in the Qdrant payload
            doc_name   = str(hit.id)
            similarity = float(hit.score)

            try:
                doc = frappe.get_doc("Career Knowledge", doc_name)
            except frappe.DoesNotExistError:
                logger.warning(
                    "KnowledgeRetriever: Career Knowledge doc %r not found in MariaDB "
                    "(stale Qdrant entry?) — skipping",
                    doc_name,
                )
                continue
            except Exception as exc:
                raise KnowledgeRetrieverError(
                    f"KnowledgeRetriever: failed to load Career Knowledge doc {doc_name!r} — {exc}"
                ) from exc

            skills    = [row.skill_name   for row in (doc.skills    or [])]
            companies = [row.company_name for row in (doc.companies or [])]

            from job_search_ai.services.knowledge.knowledge_lifecycle import KnowledgeLifecycle
            needs_ref = KnowledgeLifecycle.needs_refresh(doc)

            # 1. Embedding Similarity
            embedding_sim = similarity

            # 2. Branch Match
            branch_score = 0.5
            applicable_branches = getattr(doc, 'applicable_branches', None)
            if applicable_branches:
                branches = [b.strip().lower() for b in applicable_branches.split(",") if b.strip()]
                if student.branch.strip().lower() in branches:
                    branch_score = 1.0
                else:
                    branch_score = 0.0

            # 3. Skills Overlap
            skill_score = 1.0
            if student.skills:
                matching_skills = [s for s in student.skills if s.strip().lower() in [rs.lower() for rs in skills]]
                skill_score = len(matching_skills) / len(student.skills)

            # 4. Interest Overlap
            interest_score = 0.0
            if student.interests:
                interests_lower = [i.strip().lower() for i in student.interests]
                career_lower = (getattr(doc, 'career_name', "") or "").lower()
                industry_lower = (getattr(doc, 'industry', "") or "").lower()
                category_lower = (getattr(doc, 'category', "") or "").lower()

                # Expand student interests with synonyms to match careers/industries better
                expanded_interests = set()
                for interest in interests_lower:
                    expanded_interests.add(interest)
                    if interest in ["ai", "ml", "artificial intelligence", "machine learning", "deep learning"]:
                        expanded_interests.update(["ai", "ml", "artificial intelligence", "machine learning", "deep learning", "model"])
                    elif interest in ["frontend", "front-end", "web development", "ui", "ux", "design"]:
                        expanded_interests.update(["frontend", "front-end", "ui", "ux", "design", "developer", "web"])
                    elif interest in ["backend", "back-end", "database", "server", "sql"]:
                        expanded_interests.update(["backend", "back-end", "database", "server", "sql", "developer"])
                    elif interest in ["data science", "data analysis", "data analyst", "data scientist", "analytics"]:
                        expanded_interests.update(["data science", "data analysis", "data analyst", "data scientist", "analytics", "scientist", "data"])

                matches = 0
                for interest in expanded_interests:
                    if interest in career_lower or interest in industry_lower or interest in category_lower:
                        matches += 1
                interest_score = min(1.0, matches / max(1, len(interests_lower)))

            # 5. Country Score
            country_score = 1.0
            doc_country = getattr(doc, 'country', None)
            if student.country and doc_country:
                if student.country.strip().lower() == doc_country.strip().lower():
                    country_score = 1.0
                else:
                    country_score = 0.0

            # 6. Quality Score
            doc_quality = getattr(doc, 'quality_score', None)
            quality_score = min(1.0, (doc_quality or 70.0) / 100.0)

            # 7. Freshness Score
            freshness_score = 1.0
            doc_modified = getattr(doc, 'modified', None)
            if doc_modified:
                try:
                    from datetime import datetime
                    delta = datetime.now() - frappe.utils.to_datetime(doc_modified)
                    days_old = max(0, delta.days)
                    freshness_score = max(0.5, 1.0 - (days_old / 90.0))
                except Exception:
                    freshness_score = 1.0

            # Compute hybrid similarity score
            hybrid_similarity = (
                0.4 * embedding_sim +
                0.1 * branch_score +
                0.15 * skill_score +
                0.2 * interest_score +
                0.05 * country_score +
                0.05 * quality_score +
                0.05 * freshness_score
            )
            hybrid_similarity = round(hybrid_similarity, 4)
            # Filter by settings threshold against hybrid similarity score
            if hybrid_similarity >= self._settings.similarity_threshold:
                records.append(RetrievedKnowledge(
                    doc_name      = doc.name,
                    similarity    = hybrid_similarity,
                    hybrid_score  = hybrid_similarity,
                    career_name   = doc.career_name   or "",
                    industry      = doc.industry      or "",
                    category      = doc.category      or "",
                    country       = doc.country       or "",
                    summary       = doc.summary       or "",
                    future_demand = doc.future_demand or "",
                    career_stage  = doc.career_stage  or "",
                    confidence    = float(doc.confidence or 0.0),
                    skills        = skills,
                    companies     = companies,
                    needs_refresh = needs_ref,
                ))

        # Sort by similarity score descending
        records.sort(key=lambda r: r.similarity, reverse=True)
        return records
