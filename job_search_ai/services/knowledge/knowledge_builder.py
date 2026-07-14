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
    SkillNormalizer,
    CompanyExtractor,
    KnowledgeValidator,
)

logger = logging.getLogger(__name__)

class BuiltKnowledge:
    """Result returned by KnowledgeBuilder.build()."""

    __slots__ = ("career_name", "doc_name", "vector_id", "embedding_dim", "is_new", "timings")

    def __init__(
        self,
        career_name: str,
        doc_name: str,
        vector_id: str,
        embedding_dim: int,
        is_new: bool,
        timings: dict[str, float],
    ) -> None:
        self.career_name   = career_name
        self.doc_name      = doc_name
        self.vector_id     = vector_id
        self.embedding_dim = embedding_dim
        self.is_new        = is_new
        self.timings       = timings

    def __repr__(self) -> str:
        action = "created" if self.is_new else "updated"
        return (
            f"BuiltKnowledge({action}: {self.career_name!r}  "
            f"doc={self.doc_name!r}  dims={self.embedding_dim})"
        )


class KnowledgeBuilderError(Exception):
    """Raised by KnowledgeBuilder for any pipeline failure."""


class KnowledgeBuilder:
    """Orchestrator for the new high-quality Career Knowledge extraction pipeline.

    Processes search results through cleaning, fact extraction, skill/company
    normalization, and validation before persisting to MariaDB and Qdrant.
    """

    def __init__(
        self,
        career_name: str,
        country: str | None = None,
        embedding_service: Any | None = None,
        vector_index: Any | None = None,
    ) -> None:
        if not career_name or not str(career_name).strip():
            raise KnowledgeBuilderError("KnowledgeBuilder: career_name must be a non-empty string.")

        # Note: self._student_branch stores the student branch name passed as career_name by the agent
        self._student_branch = " ".join(str(career_name).split()).strip()
        self._country = str(country).strip() if country else None

        if embedding_service is None:
            from job_search_ai.services.ai.embedding_service import EmbeddingService
            embedding_service = EmbeddingService()
        if vector_index is None:
            from job_search_ai.services.ai.vector_index import VectorIndex
            vector_index = VectorIndex()

        self._embedding_svc = embedding_service
        self._vector_index  = vector_index

    def build(self, results: list) -> BuiltKnowledge:
        """Run the redesigned knowledge extraction pipeline on web results."""
        if not results:
            raise KnowledgeBuilderError(
                "KnowledgeBuilder.build(): results list is empty. Provide at least one SearchResult."
            )

        logger.info(
            "KnowledgeBuilder starting pipeline: student_branch=%r  country=%r  results=%d",
            self._student_branch, self._country, len(results),
        )

        timings: dict[str, float] = {}

        # Stage 1: Clean text & analyze source reliability
        t = time.perf_counter()
        cleaned_source_texts = []
        reliability_scores = []

        for r in results:
            # 1. Clean raw text content
            content = getattr(r, "content", "") or ""
            cleaned = ContentCleaner.clean(content)
            if cleaned.strip():
                title = getattr(r, "title", "") or ""
                if title.strip():
                    cleaned_source_texts.append(f"# {title.strip()}\n{cleaned}")
                else:
                    cleaned_source_texts.append(cleaned)
            
            # 2. Analyze source trust
            url = getattr(r, "url", "") or ""
            source_name = getattr(r, "source", "") or ""
            analysis = TrustedSourceAnalyzer.analyze(url, source_name)
            reliability_scores.append(analysis["reliability_score"])

        if not cleaned_source_texts:
            raise KnowledgeBuilderError("KnowledgeBuilder: all search result text content was stripped/empty.")

        # Consolidate text and calculate average reliability
        combined_cleaned_text = "\n\n".join(cleaned_source_texts)
        avg_reliability = int(sum(reliability_scores) / len(reliability_scores))
        timings["cleaning_and_source_analysis"] = time.perf_counter() - t

        # Format sources beforehand to be saved to DB for all extracted careers
        sources_list = [
            {
                "source_title": getattr(r, "title", "") or "",
                "source_url":   getattr(r, "url", "") or "",
                "publisher":    getattr(r, "source", "") or "",
                "published_on": None,
            }
            for r in results
            if getattr(r, "url", "")
        ]

        # Stage 2: Extract structured facts using LLM (list of careers)
        t = time.perf_counter()
        facts_list = CareerFactExtractor.extract_list(
            combined_cleaned_text,
            source_reliability=avg_reliability,
            country=self._country or "India"
        )
        timings["fact_extraction"] = time.perf_counter() - t

        if not facts_list:
            raise KnowledgeBuilderError("KnowledgeBuilder: failed to extract valid structured facts from content.")

        built_records = []
        normalizer = SkillNormalizer()

        for idx, facts in enumerate(facts_list):
            career_name = facts.get("career_name")
            if not career_name:
                continue

            # Populate sources list so it gets saved to MariaDB
            facts["sources"] = sources_list

            # Stage 3: Normalize skills against centralized repository
            t_skill = time.perf_counter()
            normalized_skills = normalizer.normalize_all(facts.get("skills", []), cleaned_source_texts)
            facts["skills"] = normalized_skills
            if f"skill_normalization_{idx}" not in timings:
                timings[f"skill_normalization_{idx}"] = 0.0
            timings[f"skill_normalization_{idx}"] += time.perf_counter() - t_skill

            # Stage 4: Extract and filter hiring companies
            t_comp = time.perf_counter()
            filtered_companies = CompanyExtractor.extract_and_filter(facts.get("companies", []))
            facts["companies"] = filtered_companies
            if f"company_extraction_{idx}" not in timings:
                timings[f"company_extraction_{idx}"] = 0.0
            timings[f"company_extraction_{idx}"] += time.perf_counter() - t_comp

            # Stage 5: Validate knowledge quality
            t_val = time.perf_counter()
            validation = KnowledgeValidator.validate(facts, avg_reliability)
            facts["quality_score"] = validation["quality_score"]
            if f"validation_{idx}" not in timings:
                timings[f"validation_{idx}"] = 0.0
            timings[f"validation_{idx}"] += time.perf_counter() - t_val

            logger.info(
                "KnowledgeBuilder career=%r validation result: score=%d  valid=%s",
                career_name, validation["quality_score"], validation["is_valid"]
            )

            if not validation["is_valid"]:
                continue

            # Stage 6: Persist to MariaDB
            t_db = time.perf_counter()
            doc_name, is_new = self._save_to_mariadb(facts)
            if f"db_save_{idx}" not in timings:
                timings[f"db_save_{idx}"] = 0.0
            timings[f"db_save_{idx}"] += time.perf_counter() - t_db

            # Stage 7 & 8 & 9: Generate rich semantic embedding and index (only if changed)
            embed_text = self._build_embed_text(facts)
            import hashlib
            new_hash = hashlib.md5(embed_text.encode("utf-8")).hexdigest()[:16]

            # Fetch existing embedding_hash from database
            existing_hash = None
            if not is_new:
                existing_hash = frappe.db.get_value("Career Knowledge", doc_name, "embedding_hash")

            if existing_hash == new_hash:
                logger.info("KnowledgeBuilder: embed_text unchanged for doc=%r, skipping embedding & indexing", doc_name)
                embedding_dim = 768
            else:
                t_embed = time.perf_counter()
                vector = self._embed(embed_text)
                embedding_dim = len(vector)
                if f"embedding_{idx}" not in timings:
                    timings[f"embedding_{idx}"] = 0.0
                timings[f"embedding_{idx}"] += time.perf_counter() - t_embed

                # Stage 8: Upsert into Vector Index (Qdrant)
                t_idx = time.perf_counter()
                self._index(
                    doc_name=doc_name,
                    vector=vector,
                    payload={
                        "career_name": facts["career_name"],
                        "country":     self._country or "",
                        "industry":    facts.get("industry", ""),
                        "doc_name":    doc_name,
                    },
                )
                if f"vector_upsert_{idx}" not in timings:
                    timings[f"vector_upsert_{idx}"] = 0.0
                timings[f"vector_upsert_{idx}"] += time.perf_counter() - t_idx

                # Stage 9: Write embedding hash back to MariaDB
                frappe.db.set_value(
                    "Career Knowledge", doc_name, "embedding_hash", new_hash, update_modified=False
                )
                frappe.db.commit()

            built_records.append({
                "career_name": facts["career_name"],
                "doc_name": doc_name,
                "embedding_dim": embedding_dim,
                "is_new": is_new
            })

        if not built_records:
            raise KnowledgeBuilderError("KnowledgeBuilder: all extracted careers failed validation.")

        # Return BuiltKnowledge for the first successfully built record to preserve compatibility
        first_rec = built_records[0]
        total_time = sum(timings.values())
        logger.info(
            "KnowledgeBuilder pipeline completed successfully in %.3fs: doc=%r (built %d career(s))",
            total_time, first_rec["doc_name"], len(built_records)
        )

        return BuiltKnowledge(
            career_name   = first_rec["career_name"],
            doc_name      = first_rec["doc_name"],
            vector_id     = first_rec["doc_name"],
            embedding_dim = first_rec["embedding_dim"],
            is_new        = first_rec["is_new"],
            timings       = timings,
        )

    def _save_to_mariadb(self, facts: dict[str, Any]) -> tuple[str, bool]:
        """Save normalized facts to MariaDB, using career_name and country for duplicate detection."""
        try:
            career_name = facts["career_name"]
            existing_name = self._find_existing_doc(career_name, self._country)
            
            if existing_name:
                return self._update_doc(existing_name, facts), False
            else:
                return self._create_doc(facts), True
        except Exception as exc:
            raise KnowledgeBuilderError(f"KnowledgeBuilder: MariaDB save failed: {exc}") from exc

    def _find_existing_doc(self, career_name: str, country: str | None) -> str | None:
        """Find an existing document matching career_name and country (case-insensitive)."""
        filters: dict = {"career_name": career_name}
        if country:
            filters["country"] = country
        results = frappe.get_all(
            "Career Knowledge",
            filters=filters,
            fields=["name"],
            limit=1,
        )
        return results[0]["name"] if results else None

    def _create_doc(self, facts: dict[str, Any]) -> str:
        """Create a new Career Knowledge document."""
        doc = frappe.new_doc("Career Knowledge")
        
        # Populate new applicable branch list
        facts["applicable_branches"] = self._student_branch
        
        self._populate_doc(doc, facts)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: created Career Knowledge record %r", doc.name)
        return doc.name

    def _update_doc(self, doc_name: str, facts: dict[str, Any]) -> str:
        """Update an existing Career Knowledge document and append new branch if needed."""
        doc = frappe.get_doc("Career Knowledge", doc_name)
        
        # Merge applicable branches
        existing_branches_str = doc.applicable_branches or ""
        existing_branches = [b.strip() for b in existing_branches_str.split(",") if b.strip()]
        if self._student_branch not in existing_branches:
            existing_branches.append(self._student_branch)
        
        facts["applicable_branches"] = ", ".join(existing_branches)
        
        self._populate_doc(doc, facts)
        doc.knowledge_version = (doc.knowledge_version or 1) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: updated Career Knowledge record %r (v%d)", doc.name, doc.knowledge_version)
        return doc.name

    def _populate_doc(self, doc: Any, facts: dict[str, Any]) -> None:
        """Populate document fields and child tables."""
        from job_search_ai.services.knowledge.knowledge_lifecycle import KnowledgeLifecycle

        doc.career_name  = facts["career_name"]
        doc.industry     = facts["industry"]
        doc.category     = facts["category"]
        doc.summary      = facts["summary"]
        doc.future_demand = facts["demand"]
        doc.career_stage  = facts["stage"]
        doc.confidence    = facts["confidence"]
        doc.quality_score = facts["quality_score"]
        doc.minimum_salary = facts.get("min_salary")
        doc.maximum_salary = facts.get("max_salary")
        doc.currency      = facts.get("currency") or "INR"
        doc.applicable_branches = facts.get("applicable_branches") or ""
        doc.active        = 1

        if self._country:
            doc.country = self._country

        # Automatically update lifecycle fields
        KnowledgeLifecycle.mark_refreshed(doc)

        # Populate child table: Skills
        doc.set("skills", [
            {
                "skill_name": s["skill_name"],
                "skill_type": s.get("skill_type") or "Required",
                "importance": s["importance"],
                "frequency": s["frequency"],
                "evidence_count": s["evidence_count"]
            }
            for s in facts.get("skills", [])
        ])

        # Populate child table: Companies
        doc.set("companies", [
            {"company_name": c} for c in facts.get("companies", [])
        ])

        # Populate child table: Sources
        doc.set("sources", [
            {
                "source_title": s.get("source_title", "") or s.get("title", ""),
                "source_url":   s.get("source_url", "") or s.get("url", ""),
                "publisher":    s.get("publisher", "") or s.get("source", ""),
                "published_on": s.get("published_on"),
            }
            for s in facts.get("sources", [])
        ])

    def _build_embed_text(self, facts: dict[str, Any]) -> str:
        """Construct the pipe-delimited embedding string.
        Format: Career | Industry | Category | Demand | Stage | Canonical Skills | Companies
        """
        career = facts["career_name"]
        industry = facts["industry"]
        category = facts["category"]
        demand = facts["demand"]
        stage = facts["stage"]
        
        skills_list = [s["skill_name"] for s in facts.get("skills", [])]
        skills_str = ", ".join(skills_list[:20])
        
        companies_str = ", ".join(facts.get("companies", [])[:10])

        return f"{career} | {industry} | {category} | {demand} | {stage} | {skills_str} | {companies_str}"

    def _embed(self, text: str) -> list[float]:
        try:
            return self._embedding_svc.embed(text)
        except Exception as exc:
            raise KnowledgeBuilderError(f"KnowledgeBuilder embedding failure: {exc}") from exc

    def _index(self, doc_name: str, vector: list[float], payload: dict) -> None:
        try:
            self._vector_index.upsert(id=doc_name, vector=vector, payload=payload)
        except Exception as exc:
            raise KnowledgeBuilderError(f"KnowledgeBuilder vector upsert failure: {exc}") from exc

    def _update_embedding_hash(self, doc_name: str, vector: list[float]) -> None:
        try:
            raw = ",".join(f"{v:.6f}" for v in vector[:10])
            h = hashlib.md5(raw.encode()).hexdigest()[:16]
            frappe.db.set_value(
                "Career Knowledge", doc_name, "embedding_hash", h, update_modified=False
            )
            frappe.db.commit()
        except Exception:
            logger.warning("KnowledgeBuilder could not update embedding_hash for doc=%r", doc_name)
