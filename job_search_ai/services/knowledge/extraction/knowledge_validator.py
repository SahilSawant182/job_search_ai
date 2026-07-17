# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/knowledge_validator.py

from __future__ import annotations
import re
import logging

logger = logging.getLogger(__name__)

# Very basic web noise patterns to filter out completely broken extractions
_SUMMARY_NOISE = re.compile(
    r"\b(cookie|click here|read more|advertisement|subscribe|newsletter|"
    r"sign up|get started|view all|scroll|privacy policy|terms of use)\b",
    re.IGNORECASE,
)


class KnowledgeValidator:
    """
    Validates extracted career facts and computes a Quality Score (0–100).
    Soft quality-based validation instead of rigid rule enforcement.

    Scoring dimensions (V2)
    -----------------------
    1. Source reliability     — up to 20 pts
    2. Fact completeness      — up to 30 pts  (career_name, demand, suitable_years)
    3. Suitability metadata   — up to 20 pts  (suitable_degrees + suitable_branches)
    4. Skill richness         — up to 30 pts

    Fields intentionally NOT scored (V2 — empty by design):
      industry, category, stage, summary, companies, sources, salary

    Rejection criteria (obviously broken knowledge only)
    -----------------------------------------------------
    - Career name is empty.
    - No skills extracted at all.
    - Confidence score < 30.
    - Quality score < 30.
    """

    @staticmethod
    def validate(facts: dict, source_reliability: int) -> dict:
        """
        Validate career facts and compute a Quality Score.

        Returns
        -------
        {
            "is_valid":     bool,
            "quality_score": int  (0–100),
            "reasons":      list[str]
        }
        """
        career_name = (facts.get("career_name") or "").strip()

        # Obviously broken rejections
        if not career_name:
            return {
                "is_valid": False,
                "quality_score": 0,
                "reasons": ["Career name is empty"],
            }

        # Check if career name is generic web noise
        if _SUMMARY_NOISE.search(career_name) or len(career_name) < 2 or len(career_name) > 100:
            logger.info("KnowledgeValidator: rejected noisy/malformed career title %r", career_name)
            return {
                "is_valid": False,
                "quality_score": 0,
                "reasons": [f"Noisy/malformed career title rejected: {career_name!r}"],
            }

        # Check skills existence
        skills = facts.get("skills", [])
        if not skills:
            logger.info("KnowledgeValidator: rejected %r due to empty skills", career_name)
            return {
                "is_valid": False,
                "quality_score": 0,
                "reasons": ["No skills extracted"],
            }

        # Check confidence (rejecting only obviously broken < 30)
        confidence = facts.get("confidence", 0)
        if confidence < 30:
            logger.info("KnowledgeValidator: rejected %r due to very low confidence %d", career_name, confidence)
            return {
                "is_valid": False,
                "quality_score": 0,
                "reasons": [f"Confidence score {confidence} is below absolute minimum of 30"],
            }

        score   = 0
        reasons = []

        # ── 1. Source reliability (max 20 pts) ─────────────────────────
        rel_pts = min(20, int(source_reliability * 0.20))
        score  += rel_pts
        if rel_pts < 8:
            reasons.append(f"Low source reliability: {source_reliability}")

        # ── 2. Fact completeness (max 40 pts) ──────────────────────────
        # Required core fields (10 pts each, 30 pts max)
        core_fields = ["career_name", "demand", "suitable_years"]
        for f in core_fields:
            if facts.get(f):
                score += 10
            else:
                reasons.append(f"Missing field: {f}")
        # Optional enrichment fields (bonus 5 pts each, 10 pts max)
        # industry and category are populated via heuristic inference.
        # They improve retrieval quality but are not required for validity.
        for opt_f in ["industry", "category"]:
            if facts.get(opt_f):
                score += 5

        # ── 3. Suitability metadata (max 20 pts) ────────────────────────
        degrees = (facts.get("suitable_degrees") or "").strip()
        branches = (facts.get("suitable_branches") or "").strip()
        if degrees:
            score += 15
        else:
            reasons.append("Missing suitable degrees")
        if branches:
            score += 5
        else:
            reasons.append("Missing suitable branches")

        # ── 4. Skill richness (max 30 pts) ──────────────────────────────
        # Companies are not stored in V2 — that dimension is removed.
        n_skills = len(skills)
        if n_skills > 8:
            score += 30
        elif n_skills >= 5:
            score += 22
        elif n_skills >= 3:
            score += 15
        else:
            score += 7

        # Soft validation threshold: reject only if Quality Score < 30
        quality_score = min(100, score)
        is_valid = quality_score >= 30

        if not is_valid:
            logger.info(
                "KnowledgeValidator: soft-rejected %r  score=%d  reasons=%s",
                career_name, quality_score, reasons,
            )

        return {
            "is_valid":     is_valid,
            "quality_score": quality_score,
            "reasons":      reasons,
        }
