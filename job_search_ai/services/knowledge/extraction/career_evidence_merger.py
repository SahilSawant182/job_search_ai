# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/career_evidence_merger.py
# Phase 10: Weighted consensus — source trust × agreement, not simple majority.

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

from job_search_ai.services.knowledge.extraction.career_canonicalizer import CareerCanonicalizer
from job_search_ai.services.knowledge.extraction.skill_normalizer import SkillNormalizer
from job_search_ai.services.knowledge.constants import (
    SKILL_TIER_REQUIRED_THRESHOLD,
    SKILL_TIER_PREFERRED_THRESHOLD,
)

logger = logging.getLogger(__name__)


class CareerEvidenceMerger:
    """
    Consolidates evidence from all source extractions into canonical career profiles.

    Algorithm (Phase 10)
    --------------------
    1. Group raw facts by canonical career name (via CareerCanonicalizer).
    2. For every field resolve consensus using *weighted voting*:
       - Each fact's vote weight = source_reliability_score (0–100).
       - The value with the highest total weighted votes wins.
       - For continuous fields (salary) use a weighted average.
    3. For skills, union all per-source skill-frequency maps, then re-tier
       based on evidence proportion across total sources.
    4. Build a final merged dict per career — one record per canonical name.
    """

    @staticmethod
    def merge(facts_list: list[dict], total_sources: int, source_texts: list[str] | None = None) -> list[dict]:
        """
        Merge a flat list of per-page extracted facts into canonical career profiles.

        Parameters
        ----------
        facts_list   : list of fact dicts from CareerFactExtractor.extract_list()
        total_sources: number of original search results (used for skill tiering)
        source_texts : list of original cleaned search page texts

        Returns
        -------
        list of merged fact dicts, one per canonical career name, sorted by
        evidence count (most-evidenced career first).
        """
        if not facts_list:
            return []

        # ── Step 1: Cluster by canonical career name ──────────────────────
        clusters: dict[str, list[dict]] = {}
        for fact in facts_list:
            raw_name = (fact.get("career_name") or "").strip()
            if not raw_name:
                continue
            canonical = CareerCanonicalizer.canonicalize(raw_name)
            if not canonical:
                logger.debug("CareerEvidenceMerger: dropped non-canonical %r", raw_name)
                continue
            clusters.setdefault(canonical, []).append(fact)

        if not clusters:
            return []

        normalizer = SkillNormalizer()
        merged_results: list[dict] = []

        for canonical_name, facts in clusters.items():
            merged = CareerEvidenceMerger._merge_cluster(
                canonical_name, facts, total_sources, normalizer, source_texts
            )
            merged_results.append(merged)

        # Sort by total evidence count descending (most-covered career first)
        merged_results.sort(key=lambda x: x["evidence_count"], reverse=True)
        return merged_results

    # ------------------------------------------------------------------
    # Private — merge one cluster
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_cluster(
        canonical_name: str,
        facts: list[dict],
        total_sources: int,
        normalizer: SkillNormalizer,
        source_texts: list[str] | None = None,
    ) -> dict:
        """Merge all facts in one canonical cluster into a single profile."""

        # ── Weighted-consensus helpers ────────────────────────────────────
        def _weighted_vote(field: str, fallback: str) -> str:
            """Pick the value with the highest sum of reliability-weighted votes."""
            votes: dict[str, float] = {}
            for f in facts:
                val = f.get(field)
                if not val:
                    continue
                reliability = float(f.get("source_reliability", 70))
                confidence = float(f.get("confidence", 70))
                weight = reliability * confidence
                votes[val] = votes.get(val, 0.0) + weight
            return max(votes, key=votes.__getitem__) if votes else fallback

        def _weighted_avg(field_min: str, field_max: str):
            """Weighted average over salary fields; reject year-like values."""
            mins, maxs, weights = [], [], []
            for f in facts:
                w   = float(f.get("confidence", 70))
                mn  = f.get(field_min)
                mx  = f.get(field_max)
                if mn and not (2020 <= mn <= 2030):
                    mins.append(mn * w)
                    weights.append(w)
                if mx and not (2020 <= mx <= 2030):
                    maxs.append(mx * w)
            total_w = sum(weights) or 1
            final_min = sum(mins) / total_w if mins else 0.0
            final_max = sum(maxs) / total_w if maxs else 0.0
            return final_min, final_max

        # ── Field-level consensus ─────────────────────────────────────────
        industry  = _weighted_vote("industry", "Technology")
        category  = _weighted_vote("category", "Technology")
        demand    = _weighted_vote("demand",   "Medium")
        stage     = _weighted_vote("stage",    "Growing")
        currency  = ""

        final_min, final_max = 0.0, 0.0

        # Summary is cleared per career-centric template specification
        summary = ""

        # ── Skill synthesis ───────────────────────────────────────────────
        merged_skill_freq: dict[str, int] = {}
        for f in facts:
            for token, count in (f.get("skill_freq") or {}).items():
                merged_skill_freq[token] = merged_skill_freq.get(token, 0) + count

        candidate_tokens = list(merged_skill_freq.keys())

        normalized_skills = normalizer.normalize_all(
            candidate_tokens,
            source_texts or [""],
            skill_freq=merged_skill_freq,
        )

        # Re-tier using evidence proportion relative to the max evidence count among all skills
        final_skills: list[dict] = []
        if normalized_skills:
            max_evidence = max(ns.get("evidence_count", 1) for ns in normalized_skills)
            for ns in normalized_skills:
                ev_count = ns.get("evidence_count", 1)
                proportion = ev_count / max(1, max_evidence)

                if proportion >= SKILL_TIER_REQUIRED_THRESHOLD:
                    tier = "Required"
                elif proportion >= SKILL_TIER_PREFERRED_THRESHOLD:
                    tier = "Preferred"
                else:
                    # Omit Nice To Have skills
                    continue

                ns["skill_type"] = tier
                ns["importance"] = round(proportion, 2)
                final_skills.append(ns)

        final_skills.sort(key=lambda x: x["importance"], reverse=True)

        # ── Company synthesis (omitted) ───────────────────────────────────
        companies = []

        # ── Source deduplication (omitted) ────────────────────────────────
        merged_sources: list[dict] = []

        # ── Suitable years from consensus ─────────────────────────────────
        suitable_years = _weighted_vote("suitable_years", "2,3,4")

        # ── Suitable degrees & branches union ─────────────────────────────
        degrees_set = set()
        branches_set = set()
        for f in facts:
            for d in (f.get("suitable_degrees") or "").split(","):
                d_clean = d.strip()
                if d_clean:
                    degrees_set.add(d_clean)
            for b in (f.get("suitable_branches") or "").split(","):
                b_clean = b.strip()
                if b_clean:
                    branches_set.add(b_clean)
        suitable_degrees = ", ".join(sorted(list(degrees_set)))
        suitable_branches = ", ".join(sorted(list(branches_set)))

        # ── Learning roadmap (omitted) ────────────────────────────────────
        roadmap    = ""

        # ── Confidence — weighted average across cluster ───────────────────
        conf_vals = [f.get("confidence") for f in facts if f.get("confidence")]
        confidence = int(sum(conf_vals) / len(conf_vals)) if conf_vals else 70

        evidence_count = sum(f.get("evidence_count", 1) for f in facts)

        return {
            "career_name":       canonical_name,
            "industry":          industry,
            "category":          category,
            "summary":           "",
            "demand":            demand,
            "stage":             stage,
            "suitable_degrees":  suitable_degrees,
            "suitable_branches": suitable_branches,
            "applicable_branches": suitable_branches,  # compat
            "suitable_years":    suitable_years,
            "min_salary":        final_min,
            "max_salary":        final_max,
            "currency":          currency,
            "skills":            final_skills,
            "companies":         companies,
            "sources":           merged_sources,
            "confidence":        confidence,
            "learning_roadmap":  roadmap,
            "evidence_count":    evidence_count,
        }


