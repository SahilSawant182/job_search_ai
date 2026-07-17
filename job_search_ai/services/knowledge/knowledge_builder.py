# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/knowledge_builder.py
"""
KnowledgeBuilder — orchestrates Career Knowledge persistence.

Pipeline (MISS path)
--------------------
  filtered_results  (list of SearchResult-like objects from Tavily)
        │
        ▼  Stage 1: Concatenate + clean all source texts
        │
        ▼  Stage 2: CareerLLMExtractor.extract()
        │           Returns up to 3 validated career dicts.
        │           Each dict has: career_name, required_skills, preferred_skills,
        │           suitable_degrees, suitable_branches, suitable_years,
        │           future_demand, confidence.
        │
        ▼  Stage 3: KnowledgeValidator.validate()  (soft quality gate)
        │
        ▼  Stage 4: _save_to_mariadb()  (upsert)
        │
        ▼  Stage 5: _build_embed_text() → embed → Qdrant upsert
        │           Payload: career_name, required_skills, preferred_skills,
        │                    degree, branch, years, future_demand, doc_name
        │
        ▼  MergedCareerProfile  (returned to agent — no second DB read)

Key invariants
--------------
- One document = one career role.
- Qdrant payload contains ONLY retrieval-relevant fields — no marketing text.
- Embed text is minimal: name, skills, degree, branch, years, demand.
- industry, category, summary, salary, companies, sources are NOT stored.
"""

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
    KnowledgeValidator,
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
        profiles: list,
    ):
        self.career_name   = career_name
        self.doc_name      = doc_name
        self.vector_id     = vector_id
        self.embedding_dim = embedding_dim
        self.is_new        = is_new
        self.timings       = timings
        self.profiles      = profiles

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
        self.retrieval_method = "built"

        self.career_name    = facts["career_name"]
        self.industry       = ""
        self.category       = ""
        self.country        = country or ""
        self.summary        = ""
        self.future_demand  = facts.get("future_demand", "High")
        self.career_stage   = facts.get("stage", "Growing")
        self.confidence     = float(facts.get("confidence", 70))
        self.suitable_years = facts.get("suitable_years_str", "")
        self.learning_roadmap = ""
        self.needs_refresh  = False
        self.min_salary     = None
        self.max_salary     = None
        self.suitable_degrees  = facts.get("suitable_degrees_str", "")
        self.suitable_branches = facts.get("suitable_branches_str", "")
        self.quality_score  = int(facts.get("quality_score", 70))
        self.evidence_count = 1

        # Skills
        req  = facts.get("required_skills",  [])
        pref = facts.get("preferred_skills", [])
        self.required_skills  = req
        self.preferred_skills = pref
        self.advanced_skills  = pref
        self.nice_skills      = []
        self.skills           = req + pref
        self.companies        = []

        # Skill coverage — starts at zero; RecommendationEngine will compute
        self.skill_coverage_score    = 0.0
        self.required_match_pct      = 0.0
        self.preferred_match_pct     = 0.0
        self.nice_match_pct          = 0.0
        self.matched_required_skills  = []
        self.missing_required_skills  = req[:]
        self.matched_preferred_skills = []
        self.missing_preferred_skills = pref[:]


class KnowledgeBuilderError(Exception):
    pass


# ---------------------------------------------------------------------------
# KnowledgeBuilder
# ---------------------------------------------------------------------------

class KnowledgeBuilder:
    """
    Orchestrates the Career Intelligence extraction pipeline.

    Accepts a list of Tavily search results and a career_name hint,
    extracts up to 3 structured career profiles via CareerLLMExtractor,
    persists them to MariaDB, and indexes them in Qdrant.
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
        Run the full extraction → validate → persist → embed pipeline.

        Returns a BuiltKnowledge whose .profiles list contains one
        MergedCareerProfile per valid career extracted.
        """
        if not results:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder.build(): results list is empty."
            )

        logger.info(
            "KnowledgeBuilder starting: career_focus=%r  country=%r  results=%d",
            self._career_name, self._country, len(results),
        )
        timings: dict[str, float] = {}

        # ── Stage 1: Collect and clean all source texts ─────────────────
        t = time.perf_counter()
        cleaned_texts: list[str] = []
        reliability_scores: list[int] = []

        # Only process up to the top 3 Tavily results to keep extraction fast and focused
        for r in results[:3]:
            content = getattr(r, "content", "") or ""
            cleaned = ContentCleaner.clean(content)
            if not cleaned.strip():
                continue
            # Truncate each result's clean text to 800 chars to focus on primary content/skills
            truncated_clean = cleaned[:800].strip()
            if not truncated_clean:
                continue
            url    = getattr(r, "url",    "") or ""
            source = getattr(r, "source", "") or ""
            analysis = TrustedSourceAnalyzer.analyze(url, source)
            reliability_scores.append(analysis["reliability_score"])
            cleaned_texts.append(truncated_clean)

        timings["cleaning"] = time.perf_counter() - t

        if not cleaned_texts:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder: all search results were empty after cleaning."
            )

        # Combine and cap at 2500 chars to match MAX_INPUT_CHARS in CareerLLMExtractor
        combined_text = "\n\n---\n\n".join(cleaned_texts)[:2500]

        # ── Stage 2: LLM Career Extraction ─────────────────────────────
        t = time.perf_counter()
        from job_search_ai.services.knowledge.extraction.career_llm_extractor import (
            CareerLLMExtractor,
        )
        extracted_careers = CareerLLMExtractor.extract(
            search_text=combined_text,
            career_focus=self._career_name,
        )
        timings["llm_extraction"] = time.perf_counter() - t

        if not extracted_careers:
            raise KnowledgeBuilderError(
                f"KnowledgeBuilder: CareerLLMExtractor returned no valid careers "
                f"for focus={self._career_name!r}."
            )

        avg_reliability = (
            int(sum(reliability_scores) / len(reliability_scores))
            if reliability_scores else 50
        )

        # ── Stage 3–5: Validate → persist → embed per career ──────────
        built_profiles: list[MergedCareerProfile] = []
        first_doc_name  = None
        first_is_new    = True
        first_embed_dim = 768

        for idx, career in enumerate(extracted_careers):
            career_name = career.get("career_name", "").strip()
            if not career_name:
                continue

            # Normalise degree/branch lists to comma-separated strings for DB
            degrees_list  = career.get("suitable_degrees",  [])
            branches_list = career.get("suitable_branches", [])
            years_list    = career.get("suitable_years",    [])

            career["suitable_degrees_str"]  = ", ".join(degrees_list)
            career["suitable_branches_str"] = ", ".join(branches_list)
            career["suitable_years_str"]    = ",".join(str(y) for y in years_list)

            # Stage 3: Validate
            t_val = time.perf_counter()
            validation_facts = {
                "career_name":       career_name,
                "demand":            career.get("future_demand", "High"),
                "suitable_degrees":  career["suitable_degrees_str"],
                "suitable_branches": career["suitable_branches_str"],
                "suitable_years":    career["suitable_years_str"],
                "confidence":        career.get("confidence", 70),
                "skills": (
                    [{"skill_name": s, "skill_type": "Required"} for s in career.get("required_skills", [])] +
                    [{"skill_name": s, "skill_type": "Preferred"} for s in career.get("preferred_skills", [])]
                ),
            }
            validation = KnowledgeValidator.validate(validation_facts, avg_reliability)
            career["quality_score"] = validation["quality_score"]
            timings[f"validation_{idx}"] = time.perf_counter() - t_val

            logger.info(
                "KnowledgeBuilder career=%r  quality=%d  valid=%s",
                career_name, validation["quality_score"], validation["is_valid"],
            )
            if not validation["is_valid"]:
                continue

            # Stage 4: Persist to MariaDB
            t_db = time.perf_counter()
            doc_name, is_new, existing_hash = self._save_to_mariadb(career)
            timings[f"db_save_{idx}"] = time.perf_counter() - t_db

            # Stage 5: Embed and index
            embed_text = _build_embed_text(career)
            new_hash   = hashlib.md5(embed_text.encode()).hexdigest()[:16]

            if existing_hash == new_hash:
                embed_dim = 768
            else:
                t_emb  = time.perf_counter()
                vector    = self._embed(embed_text)
                embed_dim = len(vector)
                timings[f"embed_{idx}"] = time.perf_counter() - t_emb

                # Rich Qdrant payload — contains all retrieval-relevant fields
                qdrant_payload = {
                    "career_name":     career_name,
                    "required_skills": career.get("required_skills",  []),
                    "preferred_skills": career.get("preferred_skills", []),
                    "degree":          degrees_list,
                    "branch":          branches_list,
                    "years":           years_list,
                    "future_demand":   career.get("future_demand", "High"),
                    "doc_name":        doc_name,
                }
                self._index(doc_name, vector, qdrant_payload)
                frappe.db.set_value(
                    "Career Knowledge", doc_name, "embedding_hash",
                    new_hash, update_modified=False,
                )
                frappe.db.commit()

            if first_doc_name is None:
                first_doc_name  = doc_name
                first_is_new    = is_new
                first_embed_dim = embed_dim

            profile = MergedCareerProfile(doc_name, career, self._country)
            built_profiles.append(profile)

        if not built_profiles:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder: all extracted career profiles failed validation."
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

    def _save_to_mariadb(self, career: dict) -> tuple[str, bool, str | None]:
        try:
            career_name   = career["career_name"]
            existing_name = self._find_existing_doc(career_name, self._country)
            if existing_name:
                doc_name, existing_hash = self._update_doc(existing_name, career)
                return doc_name, False, existing_hash
            doc_name = self._create_doc(career)
            return doc_name, True, None
        except Exception as exc:
            raise KnowledgeBuilderError(
                f"KnowledgeBuilder: MariaDB save failed: {exc}"
            ) from exc

    def _find_existing_doc(self, career_name: str, country: str | None) -> str | None:
        filters: dict = {"career_name": career_name}
        if country:
            filters["country"] = country
        rows = frappe.get_all(
            "Career Knowledge", filters=filters, fields=["name"], limit=1
        )
        return rows[0]["name"] if rows else None

    def _create_doc(self, career: dict) -> str:
        doc = frappe.new_doc("Career Knowledge")
        self._populate_doc(doc, career)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: created %r", doc.name)
        return doc.name

    def _update_doc(self, doc_name: str, career: dict) -> tuple[str, str | None]:
        doc = frappe.get_doc("Career Knowledge", doc_name)
        old_hash = getattr(doc, "embedding_hash", None)

        # Merge suitable_degrees / suitable_branches (union, no duplicates)
        existing_degs = {d.strip() for d in (doc.suitable_degrees or "").split(",") if d.strip()}
        new_degs      = {d.strip() for d in career.get("suitable_degrees_str", "").split(",") if d.strip()}
        career["suitable_degrees_str"] = ", ".join(sorted(existing_degs | new_degs))

        existing_brs = {b.strip() for b in (doc.suitable_branches or "").split(",") if b.strip()}
        new_brs      = {b.strip() for b in career.get("suitable_branches_str", "").split(",") if b.strip()}
        career["suitable_branches_str"] = ", ".join(sorted(existing_brs | new_brs))

        # Merge suitable_years (union)
        existing_yrs = {y.strip() for y in (doc.suitable_years or "").split(",") if y.strip()}
        new_yrs      = {y.strip() for y in career.get("suitable_years_str", "").split(",") if y.strip()}
        try:
            merged_yrs = sorted(existing_yrs | new_yrs, key=int)
        except ValueError:
            merged_yrs = sorted(existing_yrs | new_yrs)
        career["suitable_years_str"] = ",".join(merged_yrs)

        # Merge skills (union by name, keep best tier)
        existing_skill_map: dict[str, str] = {}
        for row in (doc.skills or []):
            sname = (row.get("skill_name") or "").strip()
            if sname:
                existing_skill_map[sname.lower()] = row.get("skill_type", "Required")

        new_required  = career.get("required_skills",  [])
        new_preferred = career.get("preferred_skills", [])
        for s in new_required:
            k = s.strip().lower()
            if k not in existing_skill_map:
                existing_skill_map[k] = "Required"
        for s in new_preferred:
            k = s.strip().lower()
            if k not in existing_skill_map:
                existing_skill_map[k] = "Preferred"

        # Rebuild canonical skill lists from merged map
        career["required_skills"]  = [k for k, v in existing_skill_map.items() if v == "Required"]
        career["preferred_skills"] = [k for k, v in existing_skill_map.items() if v == "Preferred"]

        self._populate_doc(doc, career)
        doc.knowledge_version = (doc.knowledge_version or 1) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: updated %r (v%d)", doc.name, doc.knowledge_version)
        return doc.name, old_hash

    def _populate_doc(self, doc: Any, career: dict) -> None:
        from job_search_ai.services.knowledge.knowledge_lifecycle import KnowledgeLifecycle

        doc.career_name      = career["career_name"]
        # Deliberately cleared fields — not stored in V3
        doc.industry         = ""
        doc.category         = ""
        doc.summary          = ""
        doc.minimum_salary   = None
        doc.maximum_salary   = None
        doc.currency         = ""
        doc.learning_roadmap = ""
        doc.source_count     = 0

        doc.future_demand    = career.get("future_demand", "High")
        doc.career_stage     = career.get("stage", "Growing")
        doc.confidence       = career.get("confidence", 70)
        doc.quality_score    = career.get("quality_score", 70)
        doc.suitable_degrees  = career.get("suitable_degrees_str", "")
        doc.suitable_branches = career.get("suitable_branches_str", "")
        doc.applicable_branches = career.get("suitable_branches_str", "")
        doc.suitable_years   = career.get("suitable_years_str", "")
        doc.active           = 1
        if self._country:
            doc.country = self._country
        KnowledgeLifecycle.mark_refreshed(doc)

        # Skills child table — Required + Preferred only
        req_skills  = career.get("required_skills",  [])
        pref_skills = career.get("preferred_skills", [])
        skill_rows = []
        for s in req_skills:
            if s and s.strip():
                skill_rows.append({
                    "skill_name":     s.strip(),
                    "skill_type":     "Required",
                    "importance":     1.0,
                    "frequency":      1,
                    "evidence_count": 1,
                })
        for s in pref_skills:
            if s and s.strip():
                skill_rows.append({
                    "skill_name":     s.strip(),
                    "skill_type":     "Preferred",
                    "importance":     0.5,
                    "frequency":      1,
                    "evidence_count": 1,
                })
        doc.set("skills", skill_rows)
        doc.set("companies", [])
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
# Module-level helpers
# ---------------------------------------------------------------------------

def _build_embed_text(career: dict) -> str:
    """
    Build minimal, clean embedding text for a career profile.

    Contains ONLY semantic career identifiers:
      career name, required skills, preferred skills,
      suitable degrees, suitable branches, suitable years, demand.

    NO JSON.  NO markdown.  NO summaries.  NO company names.  NO article text.
    NO salary.  NO roadmap.

    Why? The embedding should represent "what does this career look like"
    so that when a student's profile is embedded and compared, Qdrant
    finds the correct career — not a blog article that happens to mention
    the same keywords.
    """
    lines = [f"Career: {career['career_name']}"]

    req  = career.get("required_skills",  [])
    pref = career.get("preferred_skills", [])
    if req:
        lines.append("Required Skills:\n" + "\n".join(req[:10]))
    if pref:
        lines.append("Preferred Skills:\n" + "\n".join(pref[:6]))

    degrees_str  = career.get("suitable_degrees_str",  "")
    branches_str = career.get("suitable_branches_str", "")
    years_str    = career.get("suitable_years_str",    "")
    demand       = career.get("future_demand", "High")

    if degrees_str:
        lines.append(f"Degree:\n{degrees_str}")
    if branches_str:
        lines.append(f"Branch:\n{branches_str}")
    if years_str:
        lines.append(f"Years:\n{years_str}")
    if demand:
        lines.append(f"Demand:\n{demand}")

    return "\n\n".join(lines)


def normalize_academic_fields(value: str, is_degree: bool = False) -> str:
    """Kept for compatibility with any external callers."""
    if not value:
        return ""
    import re
    parts = re.split(r'[,;]', value)
    cleaned = []
    for p in parts:
        p = " ".join(p.strip().split())
        if not p or len(p) < 2:
            continue
        p_lower = p.lower()
        if is_degree:
            mapping = {
                "btech": "B.Tech", "b.tech": "B.Tech",
                "mtech": "M.Tech", "m.tech": "M.Tech",
                "bca": "BCA", "mca": "MCA",
                "bsc": "B.Sc", "b.sc": "B.Sc",
                "msc": "M.Sc", "m.sc": "M.Sc",
                "phd": "PhD",
            }
            p = mapping.get(p_lower, p.title())
        else:
            p = p.title()
        if p not in cleaned:
            cleaned.append(p)
    return ", ".join(sorted(cleaned))
