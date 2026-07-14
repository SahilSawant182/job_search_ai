# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/knowledge_builder.py
# Phase 9: skill merging on update + tiered embedding text + suitable_years

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
    __slots__ = ("career_name", "doc_name", "vector_id", "embedding_dim", "is_new", "timings")

    def __init__(self, career_name, doc_name, vector_id, embedding_dim, is_new, timings):
        self.career_name   = career_name
        self.doc_name      = doc_name
        self.vector_id     = vector_id
        self.embedding_dim = embedding_dim
        self.is_new        = is_new
        self.timings       = timings

    def __repr__(self):
        action = "created" if self.is_new else "updated"
        return f"BuiltKnowledge({action}: {self.career_name!r}  doc={self.doc_name!r}  dims={self.embedding_dim})"


class KnowledgeBuilderError(Exception):
    pass


class KnowledgeBuilder:
    """
    Orchestrator for the Phase 9 Career Intelligence extraction pipeline.

    Key improvements over Phase 8:
    - Individual source texts passed through for per-source skill counting
    - Skills MERGED on update (never overwritten)
    - Embedding text uses tiered skill labels (Required / Advanced / Nice)
    - suitable_years and learning_roadmap populated deterministically
    """

    def __init__(self, career_name, country=None, embedding_service=None, vector_index=None):
        if not career_name or not str(career_name).strip():
            raise KnowledgeBuilderError("KnowledgeBuilder: career_name must be a non-empty string.")
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
        if not results:
            raise KnowledgeBuilderError("KnowledgeBuilder.build(): results list is empty.")

        logger.info("KnowledgeBuilder starting: branch=%r  country=%r  results=%d",
                    self._student_branch, self._country, len(results))
        timings: dict[str, float] = {}

        # Stage 1: Clean text per source (keep individual for per-source skill counting)
        t = time.perf_counter()
        individual_cleaned: list[str] = []
        reliability_scores: list[int] = []
        sources_list: list[dict] = []

        for r in results:
            content = getattr(r, "content", "") or ""
            cleaned = ContentCleaner.clean(content)
            title   = getattr(r, "title", "")  or ""
            url     = getattr(r, "url", "")    or ""
            source  = getattr(r, "source", "") or ""

            if cleaned.strip():
                individual_cleaned.append(f"# {title.strip()}\n{cleaned}" if title.strip() else cleaned)

            analysis = TrustedSourceAnalyzer.analyze(url, source)
            reliability_scores.append(analysis["reliability_score"])
            if url:
                sources_list.append({"source_title": title, "source_url": url,
                                     "publisher": source, "published_on": None})

        if not individual_cleaned:
            raise KnowledgeBuilderError("KnowledgeBuilder: all search result content was empty.")

        combined_text = "\n\n".join(individual_cleaned)
        avg_reliability = int(sum(reliability_scores) / len(reliability_scores))
        timings["cleaning"] = time.perf_counter() - t

        # Stage 2: Extract structured facts — pass individual source texts
        t = time.perf_counter()
        facts_list = CareerFactExtractor.extract_list(
            combined_text,
            source_reliability=avg_reliability,
            country=self._country or "India",
            source_texts=individual_cleaned,   # Phase 9: per-source skill synthesis
        )
        timings["extraction"] = time.perf_counter() - t

        if not facts_list:
            raise KnowledgeBuilderError("KnowledgeBuilder: no facts extracted from content.")

        built_records = []
        normalizer = SkillNormalizer()

        for idx, facts in enumerate(facts_list):
            career_name = facts.get("career_name")
            if not career_name:
                continue

            facts["sources"] = sources_list

            # Stage 3: Normalize skills — pass skill_freq for source-count accuracy
            t_skill = time.perf_counter()
            skill_freq = facts.get("skill_freq", {})
            normalized_skills = normalizer.normalize_all(
                facts.get("skills", []),
                individual_cleaned,
                skill_freq=skill_freq,
            )
            facts["skills"] = normalized_skills
            timings[f"skill_norm_{idx}"] = time.perf_counter() - t_skill

            # Stage 4: Companies
            t_comp = time.perf_counter()
            facts["companies"] = CompanyExtractor.extract_and_filter(facts.get("companies", []))
            timings[f"company_{idx}"] = time.perf_counter() - t_comp

            # Stage 5: Validate
            t_val = time.perf_counter()
            validation = KnowledgeValidator.validate(facts, avg_reliability)
            facts["quality_score"] = validation["quality_score"]
            timings[f"validation_{idx}"] = time.perf_counter() - t_val

            logger.info("KnowledgeBuilder career=%r  score=%d  valid=%s",
                        career_name, validation["quality_score"], validation["is_valid"])

            if not validation["is_valid"]:
                continue

            # Stage 6: Persist to MariaDB (with skill merging on update)
            t_db = time.perf_counter()
            doc_name, is_new = self._save_to_mariadb(facts)
            timings[f"db_save_{idx}"] = time.perf_counter() - t_db

            # Stage 7: Embed and index (only if content changed)
            embed_text = self._build_embed_text(facts)
            new_hash = hashlib.md5(embed_text.encode("utf-8")).hexdigest()[:16]
            existing_hash = None if is_new else frappe.db.get_value("Career Knowledge", doc_name, "embedding_hash")

            if existing_hash == new_hash:
                embedding_dim = 768
            else:
                t_embed = time.perf_counter()
                vector = self._embed(embed_text)
                embedding_dim = len(vector)
                timings[f"embed_{idx}"] = time.perf_counter() - t_embed

                self._index(doc_name, vector, {
                    "career_name": facts["career_name"],
                    "country":     self._country or "",
                    "industry":    facts.get("industry", ""),
                    "doc_name":    doc_name,
                })
                frappe.db.set_value("Career Knowledge", doc_name, "embedding_hash", new_hash, update_modified=False)
                frappe.db.commit()

            built_records.append({"career_name": career_name, "doc_name": doc_name,
                                   "embedding_dim": embedding_dim, "is_new": is_new})

        if not built_records:
            raise KnowledgeBuilderError("KnowledgeBuilder: all extracted careers failed validation.")

        first = built_records[0]
        logger.info("KnowledgeBuilder done in %.3fs: %d career(s) built", sum(timings.values()), len(built_records))
        return BuiltKnowledge(first["career_name"], first["doc_name"], first["doc_name"],
                              first["embedding_dim"], first["is_new"], timings)

    # ------------------------------------------------------------------
    # MariaDB persistence
    # ------------------------------------------------------------------

    def _save_to_mariadb(self, facts: dict) -> tuple[str, bool]:
        try:
            career_name  = facts["career_name"]
            existing_name = self._find_existing_doc(career_name, self._country)
            if existing_name:
                return self._update_doc(existing_name, facts), False
            else:
                return self._create_doc(facts), True
        except Exception as exc:
            raise KnowledgeBuilderError(f"KnowledgeBuilder: MariaDB save failed: {exc}") from exc

    def _find_existing_doc(self, career_name: str, country: str | None) -> str | None:
        filters: dict = {"career_name": career_name}
        if country:
            filters["country"] = country
        results = frappe.get_all("Career Knowledge", filters=filters, fields=["name"], limit=1)
        return results[0]["name"] if results else None

    def _create_doc(self, facts: dict) -> str:
        facts["applicable_branches"] = self._student_branch
        doc = frappe.new_doc("Career Knowledge")
        self._populate_doc(doc, facts)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: created %r", doc.name)
        return doc.name

    def _update_doc(self, doc_name: str, facts: dict) -> str:
        doc = frappe.get_doc("Career Knowledge", doc_name)

        # Merge applicable branches
        existing_branches = [b.strip() for b in (doc.applicable_branches or "").split(",") if b.strip()]
        if self._student_branch not in existing_branches:
            existing_branches.append(self._student_branch)
        facts["applicable_branches"] = ", ".join(existing_branches)

        # Phase 9: Merge skills instead of overwriting
        existing_skills = [
            {"skill_name": row.skill_name, "skill_type": row.skill_type or "Required",
             "importance": float(row.importance or 0), "frequency": int(row.frequency or 1),
             "evidence_count": int(row.evidence_count or 1)}
            for row in (doc.skills or [])
        ]
        facts["skills"] = self._merge_skills(existing_skills, facts.get("skills", []))

        # Merge companies
        existing_companies = [row.company_name for row in (doc.companies or [])]
        facts["companies"] = self._merge_companies(existing_companies, facts.get("companies", []))

        self._populate_doc(doc, facts)
        doc.knowledge_version = (doc.knowledge_version or 1) + 1
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        logger.info("KnowledgeBuilder: updated %r (v%d)", doc.name, doc.knowledge_version)
        return doc.name

    def _merge_skills(self, existing: list[dict], new: list[dict]) -> list[dict]:
        """Merge new skills into existing — union by skill_name, re-score on overlap."""
        merged: dict[str, dict] = {}
        for s in existing:
            merged[s["skill_name"]] = s.copy()
        for s in new:
            name = s["skill_name"]
            if name in merged:
                # Update with higher evidence count and re-evaluate skill_type
                prev = merged[name]
                combined_evidence = prev["evidence_count"] + s["evidence_count"]
                combined_freq     = prev["frequency"] + s["frequency"]
                # Re-score skill_type based on combined evidence
                merged[name] = {
                    "skill_name":     name,
                    "skill_type":     s["skill_type"],   # new extraction is fresher
                    "importance":     max(prev["importance"], s["importance"]),
                    "frequency":      combined_freq,
                    "evidence_count": combined_evidence,
                }
            else:
                merged[name] = s.copy()
        result = sorted(merged.values(), key=lambda x: x["importance"], reverse=True)
        return result

    def _merge_companies(self, existing: list[str], new: list[str]) -> list[str]:
        seen = set(existing)
        merged = list(existing)
        for c in new:
            if c not in seen:
                seen.add(c)
                merged.append(c)
        return merged

    def _populate_doc(self, doc: Any, facts: dict) -> None:
        from job_search_ai.services.knowledge.knowledge_lifecycle import KnowledgeLifecycle

        doc.career_name      = facts["career_name"]
        doc.industry         = facts["industry"]
        doc.category         = facts["category"]
        doc.summary          = facts["summary"]
        doc.future_demand    = facts["demand"]
        doc.career_stage     = facts["stage"]
        doc.confidence       = facts["confidence"]
        doc.quality_score    = facts["quality_score"]
        doc.minimum_salary   = facts.get("min_salary")
        doc.maximum_salary   = facts.get("max_salary")
        doc.currency         = facts.get("currency") or "INR"
        doc.applicable_branches = facts.get("applicable_branches") or ""
        doc.suitable_years   = facts.get("suitable_years") or ""
        doc.learning_roadmap = facts.get("learning_roadmap") or self._build_learning_roadmap(facts)
        doc.active           = 1
        if self._country:
            doc.country = self._country
        KnowledgeLifecycle.mark_refreshed(doc)

        doc.set("skills", [
            {"skill_name": s["skill_name"], "skill_type": s.get("skill_type") or "Required",
             "importance": s["importance"], "frequency": s["frequency"],
             "evidence_count": s["evidence_count"]}
            for s in facts.get("skills", [])
        ])
        doc.set("companies", [{"company_name": c} for c in facts.get("companies", [])])
        doc.set("sources", [
            {"source_title": s.get("source_title", ""), "source_url": s.get("source_url", ""),
             "publisher": s.get("publisher", ""), "published_on": s.get("published_on")}
            for s in facts.get("sources", [])
        ])

    # ------------------------------------------------------------------
    # Embedding text — Phase 9 tiered skill labels
    # ------------------------------------------------------------------

    def _build_embed_text(self, facts: dict) -> str:
        """
        Structured, tiered embedding text for better semantic retrieval.
        Format:
            {career} | {industry} | {stage} | {demand}
            Required: {skills}
            Advanced: {skills}
            Nice: {skills}
            Companies: {companies}
        """
        career  = facts["career_name"]
        industry = facts["industry"]
        stage   = facts["stage"]
        demand  = facts["demand"]

        skills = facts.get("skills", [])
        req  = [s["skill_name"] for s in skills if s.get("skill_type") == "Required"][:10]
        adv  = [s["skill_name"] for s in skills if s.get("skill_type") == "Advanced"][:8]
        nice = [s["skill_name"] for s in skills if s.get("skill_type") == "Nice To Have"][:6]
        companies = facts.get("companies", [])[:8]

        lines = [f"{career} | {industry} | {stage} | {demand}"]
        if req:
            lines.append("Required: " + ", ".join(req))
        if adv:
            lines.append("Advanced: " + ", ".join(adv))
        if nice:
            lines.append("Nice: " + ", ".join(nice))
        if companies:
            lines.append("Companies: " + ", ".join(companies))
        return "\n".join(lines)

    @staticmethod
    def _build_learning_roadmap(facts: dict) -> str:
        """Generate a deterministic learning roadmap from skill tiers."""
        skills = facts.get("skills", [])
        req  = [s["skill_name"] for s in skills if s.get("skill_type") == "Required"][:5]
        adv  = [s["skill_name"] for s in skills if s.get("skill_type") == "Advanced"][:4]
        nice = [s["skill_name"] for s in skills if s.get("skill_type") == "Nice To Have"][:3]
        steps = req + adv + nice
        return " → ".join(steps) if steps else ""

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
