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

    Scoring dimensions
    ------------------
    1. Source reliability     — up to 20 pts
    2. Fact completeness      — up to 30 pts
    3. Suitability metadata   — up to 15 pts
    4. Skill richness         — up to 20 pts
    5. Company count          — up to 15 pts

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

        # ── 2. Fact completeness (max 30 pts, 5 pts × 6 fields) ────────
        critical_fields = ["career_name", "industry", "category", "demand", "stage", "suitable_years"]
        for f in critical_fields:
            if facts.get(f):
                score += 5
            else:
                reasons.append(f"Missing field: {f}")

        # ── 3. Suitability metadata quality (max 15 pts) ────────────────
        degrees = (facts.get("suitable_degrees") or "").strip()
        branches = (facts.get("suitable_branches") or "").strip()
        if degrees:
            score += 10
        else:
            reasons.append("Missing suitable degrees")
        if branches:
            score += 5
        else:
            reasons.append("Missing suitable branches")

        # ── 4. Skill richness (max 20 pts) ──────────────────────────────
        n_skills = len(skills)
        if n_skills > 8:
            score += 20
        elif n_skills >= 5:
            score += 15
        elif n_skills >= 3:
            score += 10
        else:
            score += 5

        # ── 5. Company count (max 15 pts) ────────────────────────────────
        companies = facts.get("companies", [])
        n_comp    = len(companies)
        if n_comp >= 3:
            score += 15
        elif n_comp >= 2:
            score += 10
        elif n_comp >= 1:
            score += 5
        else:
            reasons.append("No recognizable hiring companies found")

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
