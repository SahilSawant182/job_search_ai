# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/knowledge_builder.py

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import frappe
import frappe.utils

from job_search_ai.services.knowledge.extraction import (
    TrustedSourceAnalyzer,
    ContentCleaner,
    CareerFactExtractor,
    KnowledgeValidator,
)
from job_search_ai.services.knowledge.constants import (
    SKILL_TIER_REQUIRED_THRESHOLD,
    SKILL_TIER_PREFERRED_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

class BuiltKnowledge:
    """
    Returned by KnowledgeBuilder.build().

    Carries both the persistence identifiers (doc_name, vector_id) and the
    fully-structured merged career profiles so the caller can pass them
    directly to PromptBuilder without re-fetching from the database.
    """
    __slots__ = (
        "career_name", "doc_name", "vector_id", "embedding_dim",
        "is_new", "timings", "profiles",
    )

    def __init__(
        self,
        career_name: str,
        doc_name: str,
        vector_id: str,
        embedding_dim: int,
        is_new: bool,
        timings: dict,
        profiles: list,          # list[MergedCareerProfile]
    ):
        self.career_name   = career_name
        self.doc_name      = doc_name
        self.vector_id     = vector_id
        self.embedding_dim = embedding_dim
        self.is_new        = is_new
        self.timings       = timings
        self.profiles      = profiles   # structured, ready for PromptBuilder

    def __repr__(self):
        action = "created" if self.is_new else "updated"
        return (
            f"BuiltKnowledge({action}: {self.career_name!r}  "
            f"doc={self.doc_name!r}  dims={self.embedding_dim}  "
            f"profiles={len(self.profiles)})"
        )


class MergedCareerProfile:
    """
    Lightweight structured object representing one merged career profile.
    Exposes the same attribute interface as RetrievedKnowledge so
    Evidence.from_knowledge() can consume either type without branching.
    """
    __slots__ = (
        "doc_name", "similarity", "hybrid_score", "retrieval_method",
        "career_name", "industry", "category", "country",
        "summary", "future_demand", "career_stage",
        "confidence", "skills", "required_skills",
        "advanced_skills", "preferred_skills", "nice_skills", "companies",
        "suitable_years", "learning_roadmap", "needs_refresh",
        "min_salary", "max_salary", "suitable_degrees", "suitable_branches",
        "skill_coverage_score", "required_match_pct", "preferred_match_pct",
        "nice_match_pct",
        "matched_required_skills", "missing_required_skills",
        "matched_preferred_skills", "missing_preferred_skills",
        "quality_score", "evidence_count",
    )

    def __init__(self, doc_name: str, facts: dict, country: str | None):
        self.doc_name       = doc_name
        self.similarity     = 1.0   # freshly built — maximum relevance
        self.hybrid_score   = 1.0
        self.retrieval_method = "built"  # produced by KnowledgeBuilder MISS path

        self.career_name    = facts["career_name"]
        self.industry       = facts.get("industry", "")
        self.category       = facts.get("category", "")
        self.country        = country or ""
        self.summary        = ""
        self.future_demand  = facts.get("demand", "")
        self.career_stage   = facts.get("stage", "")
        self.confidence     = float(facts.get("confidence", 70))
        self.suitable_years = facts.get("suitable_years", "")
        self.learning_roadmap = facts.get("learning_roadmap", "")
        self.needs_refresh  = False
        self.min_salary     = facts.get("min_salary")
        self.max_salary     = facts.get("max_salary")
        self.suitable_degrees = facts.get("suitable_degrees", "")
        self.suitable_branches = facts.get("suitable_branches", "")
        self.quality_score  = int(facts.get("quality_score", 70))
        self.evidence_count = max(1, int(facts.get("evidence_count", 1)))

        # Split skills by tier for PromptBuilder consumption
        all_skills      = facts.get("skills", [])
        self.skills         = [s["skill_name"] for s in all_skills]
        self.required_skills = [
            s["skill_name"] for s in all_skills if s.get("skill_type") == "Required"
        ]
        self.preferred_skills = [
            s["skill_name"] for s in all_skills if s.get("skill_type") in ("Preferred", "Advanced")
        ]
        self.advanced_skills = self.preferred_skills
        self.nice_skills = [
            s["skill_name"] for s in all_skills if s.get("skill_type") == "Nice To Have"
        ]
        self.companies  = facts.get("companies", [])

        # Skill coverage fields — computed to zero on MISS path.
        # KnowledgeRetriever computes real values on the HIT path.
        self.skill_coverage_score    = 0.0
        self.required_match_pct      = 0.0
        self.preferred_match_pct     = 0.0
        self.nice_match_pct          = 0.0
        self.matched_required_skills  = []
        self.missing_required_skills  = self.required_skills[:]
        self.matched_preferred_skills = []
        self.missing_preferred_skills = self.preferred_skills[:]


class KnowledgeBuilderError(Exception):
    pass


# ---------------------------------------------------------------------------
# KnowledgeBuilder
# ---------------------------------------------------------------------------

class KnowledgeBuilder:
    """
    Thin orchestrator for the Career Intelligence extraction pipeline.

    Phase 10 changes
    ----------------
    - build() returns BuiltKnowledge.profiles — structured MergedCareerProfile
      objects ready for PromptBuilder.  Callers never need to re-fetch from
      MariaDB or Qdrant after a MISS-path build.
    - Embedding text contains only semantic career identifiers (no article text).
    - Skill merging on update is preserved.
    - Duplicate loops and hash checks are kept minimal.
    """

    def __init__(
        self,
        career_name: str,
        country: str | None = None,
        embedding_service=None,
        vector_index=None,
    ):
        if not career_name or not str(career_name).strip():
            raise KnowledgeBuilderError(
                "KnowledgeBuilder: career_name must be a non-empty string."
            )
        self._career_name = " ".join(str(career_name).split()).strip()
        self._country     = str(country).strip() if country else None

        if embedding_service is None:
            from job_search_ai.services.ai.embedding_service import EmbeddingService
            embedding_service = EmbeddingService()
        if vector_index is None:
            from job_search_ai.services.ai.vector_index import VectorIndex
            vector_index = VectorIndex()
        self._embedding_svc = embedding_service
        self._vector_index  = vector_index

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, results: list) -> BuiltKnowledge:
        """
        Run the full extraction → merge → validate → persist pipeline.

        Returns a BuiltKnowledge whose .profiles list contains one
        MergedCareerProfile per valid career extracted.  The agent uses
        these profiles directly for the PromptBuilder — no second DB read.
        """
        if not results:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder.build(): results list is empty."
            )

        logger.info(
            "KnowledgeBuilder starting: career=%r  country=%r  results=%d",
            self._career_name, self._country, len(results),
        )
        timings: dict[str, float] = {}

        # ── Stage 1: Extract raw facts from each source ───────────────
        t = time.perf_counter()
        all_extracted_facts: list[dict] = []
        reliability_scores: list[int]   = []
        cleaned_source_texts: list[str] = []

        # First collect all cleaned source texts
        for r in results:
            content = getattr(r, "content", "") or ""
            cleaned = ContentCleaner.clean(content)
            if cleaned.strip():
                cleaned_source_texts.append(cleaned)

        # Now extract facts per source
        for r in results:
            content = getattr(r, "content", "") or ""
            cleaned = ContentCleaner.clean(content)
            if not cleaned.strip():
                continue

            title  = getattr(r, "title",  "") or ""
            url    = getattr(r, "url",    "") or ""
            source = getattr(r, "source", "") or ""

            analysis = TrustedSourceAnalyzer.analyze(url, source)
            reliability_scores.append(analysis["reliability_score"])

            page_facts = CareerFactExtractor.extract_list(
                cleaned,
                source_reliability=analysis["reliability_score"],
                country=self._country or "India",
                source_texts=cleaned_source_texts,
                default_career_name=self._career_name,
            )
            for fact in page_facts:
                fact["sources"] = [{
                    "source_title": title,
                    "source_url":   url,
                    "publisher":    source,
                    "published_on": None,
                }]
                all_extracted_facts.append(fact)

        timings["extraction"] = time.perf_counter() - t

        if not all_extracted_facts:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder: no career facts could be extracted from search results."
            )

        # ── Stage 2: Cluster and merge evidence per canonical career ──
        t_merge = time.perf_counter()
        from job_search_ai.services.knowledge.extraction.career_evidence_merger import (
            CareerEvidenceMerger,
        )
        merged_facts = CareerEvidenceMerger.merge(
            all_extracted_facts,
            total_sources=len(cleaned_source_texts) or 1,
            source_texts=cleaned_source_texts,
        )
        timings["evidence_merging"] = time.perf_counter() - t_merge

        if not merged_facts:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder: all career candidates were filtered out."
            )

        avg_reliability = (
            int(sum(reliability_scores) / len(reliability_scores))
            if reliability_scores else 50
        )

        # ── Stage 3–5: Validate → persist → embed per career ─────────
        built_profiles: list[MergedCareerProfile] = []
        first_doc_name  = None
        first_is_new    = True
        first_embed_dim = 768

        for idx, facts in enumerate(merged_facts):
            career_name = facts.get("career_name")
            if not career_name:
                continue

            # Force pure career profile metadata defaults & clear SEO junk
            facts["industry"] = facts.get("industry") or "General"
            facts["category"] = facts.get("category") or "Professional"
            facts["demand"] = facts.get("demand") or "Medium"
            facts["stage"] = facts.get("stage") or "Growing"
            facts["summary"] = ""
            facts["sources"] = []

            # Validate
            t_val = time.perf_counter()
            validation = KnowledgeValidator.validate(facts, avg_reliability)
            facts["quality_score"] = validation["quality_score"]
            timings[f"validation_{idx}"] = time.perf_counter() - t_val

            logger.info(
                "KnowledgeBuilder career=%r  quality=%d  valid=%s",
                career_name, validation["quality_score"], validation["is_valid"],
            )
            if not validation["is_valid"]:
                continue

            # Persist to MariaDB
            t_db = time.perf_counter()
            doc_name, is_new, existing_hash = self._save_to_mariadb(facts)
            timings[f"db_save_{idx}"] = time.perf_counter() - t_db

            # Embed and index (skip if content hash unchanged)
            embed_text = _build_embed_text(facts)
            new_hash   = hashlib.md5(embed_text.encode()).hexdigest()[:16]

            if existing_hash == new_hash:
                embed_dim = 768
            else:
                t_emb = time.perf_counter()
                vector    = self._embed(embed_text)
                embed_dim = len(vector)
                timings[f"embed_{idx}"] = time.perf_counter() - t_emb

                self._index(doc_name, vector, {
                    "career_name": facts["career_name"],
                    "country":     self._country or "",
                    "industry":    facts.get("industry", ""),
                    "doc_name":    doc_name,
                })
                frappe.db.set_value(
                    "Career Knowledge", doc_name, "embedding_hash",
                    new_hash, update_modified=False,
                )
                frappe.db.commit()

            if first_doc_name is None:
                first_doc_name  = doc_name
                first_is_new    = is_new
                first_embed_dim = embed_dim

            # Build structured profile — no second DB read required
            profile = MergedCareerProfile(doc_name, facts, self._country)
            built_profiles.append(profile)

        if not built_profiles:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder: all merged career profiles failed validation."
            )

        total_t = sum(timings.values())
        logger.info(
            "KnowledgeBuilder done in %.3fs: %d career(s) built",
            total_t, len(built_profiles),
        )

        first_profile = built_profiles[0]
        return BuiltKnowledge(
            career_name   = first_profile.career_name,
            doc_name      = first_doc_name,
            vector_id     = first_doc_name,
            embedding_dim = first_embed_dim,
            is_new        = first_is_new,
            timings       = timings,
            profiles      = built_profiles,
        )

    # ------------------------------------------------------------------
    # MariaDB persistence
    # ------------------------------------------------------------------

    def _save_to_mariadb(self, facts: dict) -> tuple[str, bool, str | None]:
        try:
            career_name   = facts["career_name"]
            existing_name = self._find_existing_doc(
                career_name, self._country, facts.get("industry")
            )
            if existing_name:
                doc_name, existing_hash = self._update_doc(existing_name, facts)
                return doc_name, False, existing_hash
            doc_name = self._create_doc(facts)
            return doc_name, True, None
        except Exception as exc:
            raise KnowledgeBuilderError(
                f"KnowledgeBuilder: MariaDB save failed: {exc}"
            ) from exc

    def _find_existing_doc(
        self, career_name: str, country: str | None, industry: str | None
    ) -> str | None:
        filters: dict = {
            "career_name": career_name,
        }
        if country:
            filters["country"] = country
        rows = frappe.get_all(
            "Career Knowledge", filters=filters, fields=["name"], limit=1
        )
        return rows[0]["name"] if rows else None

    def _create_doc(self, facts: dict) -> str:
        facts["applicable_branches"] = facts.get("suitable_branches") or ""
        # Ensure skills undergo consensus-based re-tiering even on creation
        facts["skills"] = _merge_skills([], facts.get("skills", []))
        doc = frappe.new_doc("Career Knowledge")
        self._populate_doc(doc, facts)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: created %r", doc.name)
        return doc.name

    def _update_doc(self, doc_name: str, facts: dict) -> tuple[str, str | None]:
        doc = frappe.get_doc("Career Knowledge", doc_name)
        old_hash = getattr(doc, "embedding_hash", None)

        # Merge applicable branches (append without duplicating)
        existing_branches = [
            b.strip()
            for b in (doc.applicable_branches or "").split(",")
            if b.strip()
        ]
        new_brs = [b.strip() for b in (facts.get("suitable_branches") or "").split(",") if b.strip()]
        for b in new_brs:
            if b not in existing_branches:
                existing_branches.append(b)
        facts["applicable_branches"] = ", ".join(existing_branches)

        # Merge suitability fields (degrees, branches, years)
        existing_degs = {d.strip() for d in (doc.suitable_degrees or "").split(",") if d.strip()}
        new_degs = {d.strip() for d in (facts.get("suitable_degrees") or "").split(",") if d.strip()}
        facts["suitable_degrees"] = ", ".join(sorted(list(existing_degs | new_degs)))

        existing_brs = {b.strip() for b in (doc.suitable_branches or "").split(",") if b.strip()}
        new_brs = {b.strip() for b in (facts.get("suitable_branches") or "").split(",") if b.strip()}
        facts["suitable_branches"] = ", ".join(sorted(list(existing_brs | new_brs)))

        existing_yrs = {y.strip() for y in (doc.suitable_years or "").split(",") if y.strip()}
        new_yrs = {y.strip() for y in (facts.get("suitable_years") or "").split(",") if y.strip()}
        facts["suitable_years"] = ",".join(sorted(list(existing_yrs | new_yrs), key=int)) if (existing_yrs | new_yrs) else ""

        # Merge skills instead of overwriting — union by name, accumulate evidence
        existing_skills = [
            {
                "skill_name":    row.get("skill_name"),
                "skill_type":    row.get("skill_type") or "Required",
                "importance":    float(row.get("importance") or 0),
                "frequency":     int(row.get("frequency") or 1),
                "evidence_count": int(row.get("evidence_count") or 1),
            }
            for row in (doc.skills or [])
        ]
        facts["skills"] = _merge_skills(existing_skills, facts.get("skills", []))

        # Preserve existing roadmap — only rebuild from skills if it is absent
        existing_roadmap = (doc.learning_roadmap or "").strip()
        if existing_roadmap:
            facts["learning_roadmap"] = existing_roadmap
        else:
            final_skills = facts["skills"]
            req_names  = [s["skill_name"] for s in final_skills if s["skill_type"] == "Required"][:5]
            pref_names = [s["skill_name"] for s in final_skills if s["skill_type"] in ("Preferred", "Advanced")][:4]
            nice_names = [s["skill_name"] for s in final_skills if s["skill_type"] == "Nice To Have"][:3]
            facts["learning_roadmap"] = " → ".join(req_names + pref_names + nice_names)

        # Merge companies — union, preserve order
        existing_companies = [row.get("company_name") for row in (doc.companies or [])]
        facts["companies"] = _merge_companies(existing_companies, facts.get("companies", []))

        self._populate_doc(doc, facts)
        doc.knowledge_version = (doc.knowledge_version or 1) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: updated %r (v%d)", doc.name, doc.knowledge_version)
        return doc.name, old_hash

    def _populate_doc(self, doc: Any, facts: dict) -> None:
        from job_search_ai.services.knowledge.knowledge_lifecycle import KnowledgeLifecycle

        doc.career_name      = facts["career_name"]
        doc.industry         = facts["industry"]
        doc.category         = facts["category"]
        doc.summary          = ""  # DO NOT store summary/SEO text
        doc.future_demand    = facts["demand"]
        doc.career_stage     = facts["stage"]
        doc.confidence       = facts["confidence"]
        doc.quality_score    = facts["quality_score"]
        doc.minimum_salary   = facts.get("min_salary")
        doc.maximum_salary   = facts.get("max_salary")
        doc.currency         = facts.get("currency") or "INR"
        doc.applicable_branches = facts.get("applicable_branches") or ""
        doc.suitable_degrees = facts.get("suitable_degrees") or ""
        doc.suitable_branches = facts.get("suitable_branches") or ""
        doc.suitable_years   = facts.get("suitable_years") or ""
        doc.learning_roadmap = facts.get("learning_roadmap") or ""
        doc.active           = 1
        if self._country:
            doc.country = self._country
        KnowledgeLifecycle.mark_refreshed(doc)

        doc.set("skills", [
            {
                "skill_name":    s["skill_name"],
                "skill_type":    s.get("skill_type") or "Required",
                "importance":    s["importance"],
                "frequency":     s["frequency"],
                "evidence_count": s["evidence_count"],
            }
            for s in facts.get("skills", [])
        ])
        doc.set("companies", [{"company_name": c} for c in facts.get("companies", [])])
        doc.source_count = 0
        doc.set("sources", [])

    # ------------------------------------------------------------------
    # Embedding / indexing
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        try:
            return self._embedding_svc.embed(text)
        except Exception as exc:
            raise KnowledgeBuilderError(
                f"KnowledgeBuilder embedding failure: {exc}"
            ) from exc

    def _index(self, doc_name: str, vector: list[float], payload: dict) -> None:
        try:
            self._vector_index.upsert(id=doc_name, vector=vector, payload=payload)
        except Exception as exc:
            raise KnowledgeBuilderError(
                f"KnowledgeBuilder vector upsert failure: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Module-level pure helpers (no self — easy to unit-test)
# ---------------------------------------------------------------------------

def _build_embed_text(facts: dict) -> str:
    """
    Build the embedding text for a career profile.

    Contains ONLY semantic career identifiers: career name, industry,
    Required/Preferred skills, suitable degrees/branches, suitable years, demand, roadmap.
    No summaries, article text, or marketing noise.
    """
    career    = facts["career_name"]
    industry  = facts.get("industry", "")
    req_deg   = facts.get("suitable_degrees", "")
    req_br    = facts.get("suitable_branches", "")
    years     = facts.get("suitable_years", "") or facts.get("applicable_branches", "")
    demand    = facts.get("demand") or facts.get("future_demand", "Medium")
    roadmap   = facts.get("learning_roadmap", "")

    skills = facts.get("skills", [])
    req  = [s["skill_name"] for s in skills if s.get("skill_type") == "Required"][:10]
    pref = [s["skill_name"] for s in skills if s.get("skill_type") in ("Preferred", "Advanced")][:8]

    lines = [f"Career: {career}"]
    if industry:
        lines.append(f"Industry: {industry}")
    if req:
        lines.append(f"Required Skills: {', '.join(req)}")
    if pref:
        lines.append(f"Preferred Skills: {', '.join(pref)}")
    if req_deg:
        lines.append(f"Suitable Degrees: {req_deg}")
    if req_br:
        lines.append(f"Suitable Branches: {req_br}")
    if years:
        lines.append(f"Suitable Years: {years}")
    if demand:
        lines.append(f"Demand: {demand}")
    if roadmap:
        lines.append(f"Roadmap: {roadmap}")
    return "\n".join(lines)


def _merge_skills(existing: list[dict], new: list[dict]) -> list[dict]:
    """Union by skill_name, accumulate evidence counts, and re-classify tiers dynamically based on overall evidence proportion."""
    merged: dict[str, dict] = {s["skill_name"]: s.copy() for s in existing}
    for s in new:
        name = s["skill_name"]
        if not name:
            continue
        stype = s["skill_type"]
        if stype == "Advanced":
            stype = "Preferred"

        if name in merged:
            prev = merged[name]
            merged[name] = {
                "skill_name":     name,
                "importance":     max(prev["importance"], s["importance"]),
                "frequency":      prev["frequency"] + s["frequency"],
                "evidence_count": prev["evidence_count"] + s["evidence_count"],
                "skill_type":     stype,
            }
        else:
            s_copy = s.copy()
            if s_copy["skill_type"] == "Advanced":
                s_copy["skill_type"] = "Preferred"
            merged[name] = s_copy

    if merged:
        max_evidence = max(s["evidence_count"] for s in merged.values())
        for name, s in merged.items():
            prop = s["evidence_count"] / max(1, max_evidence)
            if prop >= SKILL_TIER_REQUIRED_THRESHOLD:
                s["skill_type"] = "Required"
            elif prop >= SKILL_TIER_PREFERRED_THRESHOLD:
                s["skill_type"] = "Preferred"
            else:
                s["skill_type"] = "Nice To Have"
            s["importance"] = round(prop, 2)

    return sorted(merged.values(), key=lambda x: x["importance"], reverse=True)


def _merge_companies(existing: list[str], new: list[str]) -> list[str]:
    """Union while preserving insertion order."""
    seen   = set(existing)
    result = list(existing)
    for c in new:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result
