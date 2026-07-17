# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/knowledge_retriever.py
# Phase 9: year-aware hybrid scoring + tiered skills on RetrievedKnowledge

from __future__ import annotations

import logging
import re
import time
from typing import Any, TYPE_CHECKING

import frappe
from job_search_ai.services.knowledge.constants import RetrievalWeights

if TYPE_CHECKING:
    from job_search_ai.services.settings_service import SettingsService
    from job_search_ai.agents.career_trend.schemas import StudentProfile

logger = logging.getLogger(__name__)

   
class KnowledgeRetrieverError(Exception):
    """Raised by KnowledgeRetriever for any retrieval pipeline failure."""


class RetrievedKnowledge:
    """A single Career Knowledge record returned by KnowledgeRetriever."""

    __slots__ = (
        "doc_name", "similarity", "hybrid_score", "retrieval_method",
        "career_name", "industry", "category", "country",
        "summary", "future_demand", "career_stage", "confidence",
        "skills", "required_skills", "advanced_skills", "preferred_skills",
        "nice_skills", "companies", "suitable_years", "learning_roadmap",
        "needs_refresh", "suitable_degrees", "suitable_branches",
        "skill_coverage_score", "required_match_pct", "preferred_match_pct",
        "nice_match_pct",
        "matched_required_skills", "missing_required_skills",
        "matched_preferred_skills", "missing_preferred_skills",
        "quality_score", "evidence_count",
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
        preferred_skills: list[str] | None = None,
        nice_skills: list[str] | None = None,
        companies: list[str] | None = None,
        suitable_years: str = "",
        learning_roadmap: str = "",
        needs_refresh: bool = False,
        suitable_degrees: str = "",
        suitable_branches: str = "",
        skill_coverage_score: float = 0.0,
        required_match_pct: float = 0.0,
        preferred_match_pct: float = 0.0,
        nice_match_pct: float = 0.0,
        matched_required_skills: list[str] | None = None,
        missing_required_skills: list[str] | None = None,
        matched_preferred_skills: list[str] | None = None,
        missing_preferred_skills: list[str] | None = None,
        retrieval_method: str = "vector",
        quality_score: int = 70,
        evidence_count: int = 1,
    ) -> None:
        self.doc_name        = doc_name
        self.similarity      = similarity
        self.hybrid_score    = hybrid_score
        self.retrieval_method = retrieval_method
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
        self.preferred_skills = preferred_skills or []
        self.advanced_skills = advanced_skills or self.preferred_skills
        self.nice_skills     = nice_skills or []
        self.companies       = companies or []
        self.suitable_years  = suitable_years
        self.learning_roadmap = learning_roadmap
        self.needs_refresh   = needs_refresh
        self.suitable_degrees = suitable_degrees
        self.suitable_branches = suitable_branches
        self.skill_coverage_score = skill_coverage_score
        self.required_match_pct   = required_match_pct
        self.preferred_match_pct  = preferred_match_pct
        self.nice_match_pct       = nice_match_pct
        self.matched_required_skills  = matched_required_skills or []
        self.missing_required_skills  = missing_required_skills or []
        self.matched_preferred_skills = matched_preferred_skills or []
        self.missing_preferred_skills = missing_preferred_skills or []
        self.quality_score   = quality_score
        self.evidence_count  = evidence_count

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

        records = []
        if vector_hits:
            t = time.perf_counter()
            records = self._load_from_mariadb(vector_hits, student)
            timings["db_fetch"] = time.perf_counter() - t

        max_similarity = max(r.similarity for r in records) if records else 0.0
        threshold = float(self._settings.similarity_threshold)

        if not records or max_similarity < threshold:
            fallback_records = self._fallback_name_match(student, threshold)
            if fallback_records:
                logger.info("KnowledgeRetriever: direct name match fallback found %d record(s)", len(fallback_records))
                return fallback_records

        logger.info("KnowledgeRetriever: loaded=%d  max_sim=%.4f  total=%.3fs",
                    len(records), max_similarity, sum(timings.values()))
        return records

    def _fallback_name_match(self, student: "StudentProfile", threshold: float) -> list[RetrievedKnowledge]:
        """
        Broader metadata-based fallback when vector search yields no strong hit.

        Searches Career Knowledge records by:
          - Canonical career name (from student interests or branch)
          - Required/preferred skills overlap
          - Student branch / suitable_branches text match

        Records found here are tagged retrieval_method='metadata'.
        Similarity is NOT fabricated — hybrid scoring from _load_from_mariadb
        uses the real student context signals.
        """
        from job_search_ai.services.knowledge.extraction.career_canonicalizer import CareerCanonicalizer

        # Build canonical name targets from student context
        name_targets: list[str] = []
        if student.interests:
            for interest in student.interests[:3]:
                canonical = CareerCanonicalizer.canonicalize(interest)
                if canonical and canonical not in name_targets:
                    name_targets.append(canonical)
        if student.branch:
            canonical = CareerCanonicalizer.canonicalize(student.branch)
            if canonical and canonical not in name_targets:
                name_targets.append(canonical)

        # Collect candidate doc names from multiple search dimensions
        matched_doc_names: list[str] = []
        seen: set[str] = set()

        # 1. Exact career name match
        for target in name_targets:
            rows = frappe.get_all(
                "Career Knowledge",
                filters={"career_name": target, "active": 1},
                fields=["name"],
                limit=2,
            )
            for row in rows:
                if row["name"] not in seen:
                    seen.add(row["name"])
                    matched_doc_names.append(row["name"])

        # 2. Branch / suitable_branches text overlap (LIKE match on student branch)
        if student.branch and len(matched_doc_names) < 3:
            branch_word = student.branch.split()[0] if student.branch.split() else ""
            if branch_word and len(branch_word) > 3:
                rows = frappe.get_all(
                    "Career Knowledge",
                    filters=[
                        ["active", "=", 1],
                        ["suitable_branches", "like", f"%{branch_word}%"],
                    ],
                    fields=["name"],
                    limit=3,
                )
                for row in rows:
                    if row["name"] not in seen:
                        seen.add(row["name"])
                        matched_doc_names.append(row["name"])

        # 3. Skill name overlap — search for docs that mention a student skill
        if student.skills and len(matched_doc_names) < 3:
            for skill in student.skills[:3]:
                rows = frappe.db.sql(
                    """
                    SELECT DISTINCT ck.name
                    FROM `tabCareer Knowledge` ck
                    JOIN `tabCareer Knowledge Skill` cs ON cs.parent = ck.name
                    WHERE ck.active = 1
                      AND cs.skill_name LIKE %(skill)s
                    LIMIT 2
                    """,
                    {"skill": f"%{skill}%"},
                    as_dict=True,
                )
                for row in rows:
                    if row["name"] not in seen:
                        seen.add(row["name"])
                        matched_doc_names.append(row["name"])
                if len(matched_doc_names) >= 3:
                    break

        if not matched_doc_names:
            return []

        # Use a stub hit with score=0.0 — hybrid scoring from _load_from_mariadb
        # provides the real relevance signals; we never fabricate vector similarity.
        class _MetadataHit:
            def __init__(self, doc_id: str):
                self.id = doc_id
                self.score = 0.0  # no vector score available

        stub_hits = [_MetadataHit(name) for name in matched_doc_names]
        records = self._load_from_mariadb(stub_hits, student)

        # Tag as metadata retrieval — do NOT overwrite similarity
        for r in records:
            r.retrieval_method = "metadata"

        # Return records that clear the threshold after hybrid scoring
        return [r for r in records if r.hybrid_score >= max(0.40, threshold - 0.20)]

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
            base_threshold = float(self._settings.similarity_threshold)
            vector_threshold = max(0.40, base_threshold - 0.20)
            return self._vector_index.search(
                query_vector    = vector,
                limit           = 25,
                score_threshold = vector_threshold,
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
            preferred_skills = []
            nice_skills     = []
            for row in (doc.skills or []):
                sname = row.get("skill_name")
                stype = (row.get("skill_type") or "Required")
                all_skills.append(sname)
                if stype == "Required":
                    required_skills.append(sname)
                elif stype in ("Preferred", "Advanced"):
                    preferred_skills.append(sname)
                else:
                    nice_skills.append(sname)

            companies = [row.get("company_name") for row in (doc.companies or [])]

            from job_search_ai.services.knowledge.knowledge_lifecycle import KnowledgeLifecycle
            needs_ref = KnowledgeLifecycle.needs_refresh(doc)

            # ── Hybrid Score ────────────────────────────────────────────
            embedding_sim = similarity

            # 1. Academic match (Branch & Degree) with robust synonym/umbrella mapping
            branch_score = 0.5
            applicable_branches = getattr(doc, "suitable_branches", None) or getattr(doc, "applicable_branches", None)
            if applicable_branches:
                branches = [b.strip().lower() for b in applicable_branches.split(",") if b.strip()]
                sb_lower = student.branch.strip().lower()

                if sb_lower in branches:
                    branch_score = 1.0
                else:
                    # CS/IT umbrella match
                    cs_it_umbrella = {"computer", "cs", "cse", "it", "information", "software", "web", "systems", "network", "programming", "development"}
                    student_is_cs = any(kw in sb_lower for kw in cs_it_umbrella)

                    # Business/Marketing umbrella match
                    biz_marketing_umbrella = {"marketing", "business", "administration", "strategy", "management", "mba", "finance", "sales"}
                    student_is_biz = any(kw in sb_lower for kw in biz_marketing_umbrella)

                    matched = False
                    for b in branches:
                        if student_is_cs and any(kw in b for kw in cs_it_umbrella):
                            matched = True
                            break
                        if student_is_biz and any(kw in b for kw in biz_marketing_umbrella):
                            matched = True
                            break
                        b_words = set(re.findall(r'\w+', b)) - {"and", "engineering", "technology", "science"}
                        student_words = set(re.findall(r'\w+', sb_lower)) - {"and", "engineering", "technology", "science"}
                        if student_words & b_words:
                            matched = True
                            break

                    branch_score = 0.8 if matched else (0.0 if branches else 0.5)

            degree_score = 0.5
            suitable_degrees = getattr(doc, "suitable_degrees", None)
            if suitable_degrees:
                degrees = [d.strip().lower() for d in suitable_degrees.split(",") if d.strip()]
                sd_lower = student.degree.strip().lower()

                if sd_lower in degrees:
                    degree_score = 1.0
                else:
                    # Check for engineering synonyms
                    eng_synonyms = {"engineering", "technology", "tech", "b.tech", "btech", "m.tech", "mtech", "b.e", "b.e.", "m.e", "m.e."}
                    student_is_eng = any(kw in sd_lower for kw in eng_synonyms)

                    # Check for general computer science / tech degrees
                    comp_keywords = {"computer", "cs", "it", "information", "mca", "science"}
                    student_is_comp = any(kw in sd_lower for kw in comp_keywords)

                    matched = False
                    for d in degrees:
                        if student_is_eng and any(kw in d for kw in eng_synonyms):
                            matched = True
                            break
                        if student_is_comp and any(kw in d for kw in comp_keywords):
                            matched = True
                            break
                        d_words = set(re.findall(r'\w+', d)) - {"and", "degree", "of", "science", "arts", "bachelor", "master"}
                        student_words = set(re.findall(r'\w+', sd_lower)) - {"and", "degree", "of", "science", "arts", "bachelor", "master"}
                        if student_words & d_words:
                            matched = True
                            break

                    degree_score = 0.8 if matched else (0.0 if degrees else 0.5)

            academic_match_score = (branch_score + degree_score) / 2.0

            # 2. Skill coverage score (weighted compliance) with substring/variation matching
            required_coverage = 0.0
            preferred_coverage = 0.0
            nice_coverage = 0.0
            skill_coverage_score = 0.0
            matched_req: list[str] = []
            missing_req: list[str] = []
            matched_pref: list[str] = []
            missing_pref: list[str] = []

            if student.skills:
                student_lower = {s.strip().lower() for s in student.skills}

                # Helper function for substring skill matching
                def is_skill_match(skill_name: str) -> bool:
                    s_low = skill_name.strip().lower()
                    for stu in student_lower:
                        if len(stu) <= 2:
                            if stu == s_low:
                                return True
                        else:
                            if stu in s_low or s_low in stu:
                                return True
                    return False

                matched_req  = [s for s in required_skills  if is_skill_match(s)]
                missing_req  = [s for s in required_skills  if not is_skill_match(s)]
                matched_pref = [s for s in preferred_skills if is_skill_match(s)]
                missing_pref = [s for s in preferred_skills if not is_skill_match(s)]

                required_coverage  = len(matched_req)  / len(required_skills)  if required_skills  else 1.0
                preferred_coverage = len(matched_pref) / len(preferred_skills) if preferred_skills else 1.0
                nice_set = {s.lower() for s in nice_skills}
                nice_coverage = sum(1 for s in nice_skills if is_skill_match(s)) / len(nice_skills) if nice_skills else 1.0

                skill_coverage_score = 0.7 * required_coverage + 0.2 * preferred_coverage + 0.1 * nice_coverage

            # 3. Interest overlap with synonym expansion
            interest_score = 0.0
            if student.interests:
                interests_lower = [i.strip().lower() for i in student.interests]
                career_lower    = (doc.career_name or "").lower()

                expanded = set(interests_lower)
                # Dynamic word-level tokenisation to find matches naturally without hardcoding
                for interest in interests_lower:
                    words = [w for w in re.findall(r'\w+', interest) if len(w) > 2]
                    expanded.update(words)

                matches = sum(1 for i in expanded if i in career_lower)
                interest_score = min(1.0, matches / max(1, len(interests_lower)))

            # 4. Year–stage match (Phase 9 NEW)
            year_stage_score = self._compute_year_stage_score(student.year, doc.career_stage or "")

            # 5. Country match
            country_score = 1.0
            doc_country = getattr(doc, "country", None)
            if student.country and doc_country:
                country_score = 1.0 if student.country.strip().lower() == doc_country.strip().lower() else 0.0

            # 6. Quality score
            db_quality_score = int(getattr(doc, "quality_score", None) or 70)
            db_evidence_count = max(1, int(getattr(doc, "source_count", None) or 1))
            quality_score = min(1.0, db_quality_score / 100.0)

            hybrid_similarity = round(
                RetrievalWeights.VECTOR   * embedding_sim +
                RetrievalWeights.INTEREST * interest_score +
                RetrievalWeights.SKILL    * skill_coverage_score +
                RetrievalWeights.ACADEMIC * academic_match_score +
                RetrievalWeights.YEAR     * year_stage_score +
                RetrievalWeights.COUNTRY  * country_score +
                RetrievalWeights.QUALITY  * quality_score,
                4,
            )
            if hybrid_similarity >= max(0.40, float(self._settings.similarity_threshold) - 0.20):
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
                    advanced_skills  = preferred_skills,
                    preferred_skills = preferred_skills,
                    nice_skills      = nice_skills,
                    companies        = companies,
                    suitable_years   = getattr(doc, "suitable_years", "") or "",
                    learning_roadmap = getattr(doc, "learning_roadmap", "") or "",
                    needs_refresh    = needs_ref,
                    suitable_degrees = getattr(doc, "suitable_degrees", "") or "",
                    suitable_branches = getattr(doc, "suitable_branches", "") or "",
                    skill_coverage_score = skill_coverage_score,
                    required_match_pct   = required_coverage,
                    preferred_match_pct  = preferred_coverage,
                    nice_match_pct       = nice_coverage,
                    matched_required_skills  = matched_req,
                    missing_required_skills  = missing_req,
                    matched_preferred_skills = matched_pref,
                    missing_preferred_skills = missing_pref,
                    retrieval_method         = "vector",
                    quality_score            = db_quality_score,
                    evidence_count           = db_evidence_count,
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
      