# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/knowledge_retriever.py
# Phase 9: year-aware hybrid scoring + tiered skills on RetrievedKnowledge

from __future__ import annotations

import logging
import time
from typing import Any, TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from job_search_ai.services.settings_service import SettingsService
    from job_search_ai.agents.career_trend.schemas import StudentProfile

logger = logging.getLogger(__name__)


class KnowledgeRetrieverError(Exception):
    """Raised by KnowledgeRetriever for any retrieval pipeline failure."""


class RetrievedKnowledge:
    """A single Career Knowledge record returned by KnowledgeRetriever.

    Phase 9 additions:
        required_skills  — skills with skill_type == Required
        advanced_skills  — skills with skill_type == Advanced
        nice_skills      — skills with skill_type == Nice To Have
        suitable_years   — e.g. "3,4"
        learning_roadmap — e.g. "HTML → CSS → React"
    """

    __slots__ = (
        "doc_name", "similarity", "hybrid_score",
        "career_name", "industry", "category", "country",
        "summary", "future_demand", "career_stage", "confidence",
        "skills", "required_skills", "advanced_skills", "nice_skills",
        "companies", "suitable_years", "learning_roadmap", "needs_refresh",
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
        required_skills: list[str] | None = None,
        advanced_skills: list[str] | None = None,
        nice_skills: list[str] | None = None,
        companies: list[str] | None = None,
        suitable_years: str = "",
        learning_roadmap: str = "",
        needs_refresh: bool = False,
    ) -> None:
        self.doc_name        = doc_name
        self.similarity      = similarity
        self.hybrid_score    = hybrid_score
        self.career_name     = career_name
        self.industry        = industry
        self.category        = category
        self.country         = country
        self.summary         = summary
        self.future_demand   = future_demand
        self.career_stage    = career_stage
        self.confidence      = confidence
        self.skills          = skills or []
        self.required_skills = required_skills or []
        self.advanced_skills = advanced_skills or []
        self.nice_skills     = nice_skills or []
        self.companies       = companies or []
        self.suitable_years  = suitable_years
        self.learning_roadmap = learning_roadmap
        self.needs_refresh   = needs_refresh

    def __repr__(self) -> str:
        return (
            f"RetrievedKnowledge(doc={self.doc_name!r}  career={self.career_name!r}  "
            f"similarity={self.similarity:.4f}  hybrid={self.hybrid_score:.4f})"
        )


class KnowledgeRetriever:
    """
    Retrieve relevant Career Knowledge records for a StudentProfile.
    Phase 9: year-aware hybrid scoring.

    Hybrid Score Weights
    --------------------
    0.35 × vector_similarity
    0.10 × branch_match
    0.15 × skill_overlap   (required skills weighted more)
    0.15 × interest_overlap
    0.10 × year_stage_match   ← Phase 9 NEW
    0.05 × country_match
    0.05 × quality_score
    0.05 × freshness_score
    """

    def __init__(self, settings=None, embedding_service=None, vector_index=None):
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

    def retrieve(self, student: "StudentProfile") -> list[RetrievedKnowledge]:
        timings: dict[str, float] = {}

        search_text = self._build_search_text(student)
        logger.info("KnowledgeRetriever: search_text=%r  threshold=%.2f  limit=%d",
                    search_text, self._settings.similarity_threshold, self._settings.max_retrieved_knowledge)

        t = time.perf_counter()
        vector = self._embed(search_text)
        timings["embedding"] = time.perf_counter() - t

        t = time.perf_counter()
        vector_hits = self._search_vector_index(vector)
        timings["vector_search"] = time.perf_counter() - t
        logger.info("KnowledgeRetriever: vector hits=%d  elapsed=%.3fs", len(vector_hits), timings["vector_search"])

        if not vector_hits:
            return []

        t = time.perf_counter()
        records = self._load_from_mariadb(vector_hits, student)
        timings["db_fetch"] = time.perf_counter() - t

        avg_similarity = sum(r.similarity for r in records) / len(records) if records else 0.0
        logger.info("KnowledgeRetriever: loaded=%d  avg_sim=%.4f  total=%.3fs",
                    len(records), avg_similarity, sum(timings.values()))
        return records

    @staticmethod
    def _build_search_text(student: "StudentProfile") -> str:
        parts: list[str] = []
        if student.interests:
            parts.append(", ".join(student.interests[:3]))
        if student.skills:
            parts.append("skills: " + ", ".join(student.skills[:8]))
        if student.branch:
            parts.append(student.branch)
        if student.country:
            parts.append(student.country)
        return " | ".join(parts) if parts else student.branch

    def _embed(self, text: str) -> list[float]:
        try:
            return self._embedding_svc.embed(text)
        except Exception as exc:
            raise KnowledgeRetrieverError(f"Embedding failed: {exc}") from exc

    def _search_vector_index(self, vector: list[float]) -> list:
        try:
            return self._vector_index.search(
                query_vector    = vector,
                limit           = self._settings.max_retrieved_knowledge,
                score_threshold = self._settings.similarity_threshold,
            )
        except Exception as exc:
            raise KnowledgeRetrieverError(f"Vector search failed: {exc}") from exc

    def _load_from_mariadb(self, vector_hits: list, student: "StudentProfile") -> list[RetrievedKnowledge]:
        records: list[RetrievedKnowledge] = []

        for hit in vector_hits:
            doc_name   = str(hit.id)
            similarity = float(hit.score)

            try:
                doc = frappe.get_doc("Career Knowledge", doc_name)
            except frappe.DoesNotExistError:
                logger.warning("KnowledgeRetriever: doc %r not in MariaDB (stale) — skipping", doc_name)
                continue
            except Exception as exc:
                raise KnowledgeRetrieverError(f"Failed to load {doc_name!r}: {exc}") from exc

            # Separate skills by tier
            all_skills      = []
            required_skills = []
            advanced_skills = []
            nice_skills     = []
            for row in (doc.skills or []):
                sname = row.skill_name
                stype = (row.skill_type or "Required")
                all_skills.append(sname)
                if stype == "Required":
                    required_skills.append(sname)
                elif stype == "Advanced":
                    advanced_skills.append(sname)
                else:
                    nice_skills.append(sname)

            companies = [row.company_name for row in (doc.companies or [])]

            from job_search_ai.services.knowledge.knowledge_lifecycle import KnowledgeLifecycle
            needs_ref = KnowledgeLifecycle.needs_refresh(doc)

            # ── Hybrid Score ────────────────────────────────────────────
            embedding_sim = similarity

            # 1. Branch match
            branch_score = 0.5
            applicable_branches = getattr(doc, "applicable_branches", None)
            if applicable_branches:
                branches = [b.strip().lower() for b in applicable_branches.split(",") if b.strip()]
                if student.branch.strip().lower() in branches:
                    branch_score = 1.0
                elif branches:
                    branch_score = 0.0

            # 2. Required-skill overlap (Phase 9: weight required skills more)
            skill_score = 1.0
            if student.skills:
                req_set = {s.lower() for s in required_skills}
                all_set = {s.lower() for s in all_skills}
                student_lower = [s.strip().lower() for s in student.skills]
                req_matches = sum(1 for s in student_lower if s in req_set)
                all_matches = sum(1 for s in student_lower if s in all_set)
                n = len(student.skills)
                # Required matches weighted 70%, all-skill matches 30%
                skill_score = (req_matches / n * 0.7 + all_matches / n * 0.3) if n else 1.0

            # 3. Interest overlap with synonym expansion
            interest_score = 0.0
            if student.interests:
                interests_lower = [i.strip().lower() for i in student.interests]
                career_lower    = (doc.career_name or "").lower()
                industry_lower  = (doc.industry    or "").lower()
                category_lower  = (doc.category    or "").lower()

                expanded = set(interests_lower)
                for interest in interests_lower:
                    if interest in {"ai", "ml", "machine learning", "artificial intelligence", "deep learning"}:
                        expanded.update({"ai", "ml", "machine learning", "artificial intelligence", "model"})
                    elif interest in {"frontend", "front-end", "web development", "ui", "ux"}:
                        expanded.update({"frontend", "front-end", "ui", "ux", "developer", "web"})
                    elif interest in {"backend", "back-end", "database", "server", "sql"}:
                        expanded.update({"backend", "back-end", "database", "server", "developer"})
                    elif interest in {"data science", "data analysis", "data analyst", "analytics"}:
                        expanded.update({"data science", "data", "analytics", "scientist"})
                    elif interest in {"devops", "cloud", "infrastructure"}:
                        expanded.update({"devops", "cloud", "infrastructure", "platform"})

                matches = sum(1 for i in expanded if i in career_lower or i in industry_lower or i in category_lower)
                interest_score = min(1.0, matches / max(1, len(interests_lower)))

            # 4. Year–stage match (Phase 9 NEW)
            year_stage_score = self._compute_year_stage_score(student.year, doc.career_stage or "")

            # 5. Country match
            country_score = 1.0
            doc_country = getattr(doc, "country", None)
            if student.country and doc_country:
                country_score = 1.0 if student.country.strip().lower() == doc_country.strip().lower() else 0.0

            # 6. Quality score
            quality_score = min(1.0, (getattr(doc, "quality_score", None) or 70.0) / 100.0)

            # 7. Freshness score
            freshness_score = 1.0
            doc_modified = getattr(doc, "modified", None)
            if doc_modified:
                try:
                    from datetime import datetime
                    delta = datetime.now() - frappe.utils.to_datetime(doc_modified)
                    freshness_score = max(0.5, 1.0 - (max(0, delta.days) / 90.0))
                except Exception:
                    pass

            hybrid_similarity = round(
                0.35 * embedding_sim +
                0.10 * branch_score +
                0.15 * skill_score +
                0.15 * interest_score +
                0.10 * year_stage_score +    # Phase 9 NEW
                0.05 * country_score +
                0.05 * quality_score +
                0.05 * freshness_score,
                4,
            )

            if hybrid_similarity >= self._settings.similarity_threshold:
                records.append(RetrievedKnowledge(
                    doc_name         = doc.name,
                    similarity       = hybrid_similarity,
                    hybrid_score     = hybrid_similarity,
                    career_name      = doc.career_name   or "",
                    industry         = doc.industry      or "",
                    category         = doc.category      or "",
                    country          = doc.country       or "",
                    summary          = doc.summary       or "",
                    future_demand    = doc.future_demand or "",
                    career_stage     = doc.career_stage  or "",
                    confidence       = float(doc.confidence or 0.0),
                    skills           = all_skills,
                    required_skills  = required_skills,
                    advanced_skills  = advanced_skills,
                    nice_skills      = nice_skills,
                    companies        = companies,
                    suitable_years   = getattr(doc, "suitable_years", "") or "",
                    learning_roadmap = getattr(doc, "learning_roadmap", "") or "",
                    needs_refresh    = needs_ref,
                ))

        records.sort(key=lambda r: r.similarity, reverse=True)
        return records

    @staticmethod
    def _compute_year_stage_score(student_year: int, career_stage: str) -> float:
        """
        Score how well the career stage matches the student's academic year.

        Year 4 → Immediate Placement = 1.0, Growing = 0.5, Future = 0.0
        Year 1 → Future = 1.0, Growing = 0.7, Immediate = 0.4
        Year 2-3 → Growing = 1.0, Immediate = 0.7, Future = 0.5
        """
        stage = career_stage.strip() if career_stage else ""
        if student_year >= 4:
            return {"Immediate Placement": 1.0, "Growing": 0.5, "Future": 0.0}.get(stage, 0.5)
        elif student_year == 1:
            return {"Future": 1.0, "Growing": 0.7, "Immediate Placement": 0.4}.get(stage, 0.6)
        else:  # Year 2-3
            return {"Growing": 1.0, "Immediate Placement": 0.7, "Future": 0.5}.get(stage, 0.7)
