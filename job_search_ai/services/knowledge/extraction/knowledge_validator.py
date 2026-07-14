# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/knowledge_validator.py
# Phase 10: Stricter validation — career name, skills, summary, companies, evidence.

from __future__ import annotations
import re
import logging

logger = logging.getLogger(__name__)


# Patterns that identify marketing/SEO article titles, not careers.
_MARKETING_PATTERNS = re.compile(
    r"\b(guide|salary guide|salary|interview questions?|how to|top \d+|top five|"
    r"top ten|best \d+|roadmap|tutorial|course|become|complete guide|syllabus|"
    r"resume|vs\.?|versus|2024|2025|2026|review|comparison|learn|scope|"
    r"everything you need|what is|explained|overview|career path|for beginners?)\b",
    re.IGNORECASE,
)

# A career name should resemble a real job title: 2–6 words, no punctuation noise.
_CAREER_TITLE_RE = re.compile(r"^[A-Z][a-zA-Z0-9 /+#\-]{2,60}$")

# Summary noise — web boilerplate that should never appear in a career summary.
_SUMMARY_NOISE = re.compile(
    r"\b(cookie|click here|read more|advertisement|subscribe|newsletter|"
    r"sign up|get started|view all|scroll|privacy policy|terms of use)\b",
    re.IGNORECASE,
)


class KnowledgeValidator:
    """
    Validates extracted career facts and computes a Quality Score (0–100).

    Scoring dimensions
    ------------------
    1. Source reliability     — up to 20 pts
    2. Fact completeness      — up to 30 pts  (6 critical fields × 5)
    3. Summary quality        — up to 15 pts
    4. Skill count & quality  — up to 20 pts
    5. Company count          — up to 15 pts

    Rejection criteria (any one is sufficient to reject)
    ----------------------
    - Career name is empty or matches a marketing/SEO title pattern.
    - Career name does not look like a real job title.
    - No skills extracted at all.
    - Quality score < 50.
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

        # Hard rejection: missing or marketing career name
        if not career_name:
            return {"is_valid": False, "quality_score": 0,
                    "reasons": ["Career name is empty"]}

        if _MARKETING_PATTERNS.search(career_name):
            logger.info("KnowledgeValidator: rejected marketing title %r", career_name)
            return {
                "is_valid": False,
                "quality_score": 0,
                "reasons": [f"Marketing/SEO title rejected: {career_name!r}"],
            }

        if not _CAREER_TITLE_RE.match(career_name):
            logger.info("KnowledgeValidator: rejected malformed title %r", career_name)
            return {
                "is_valid": False,
                "quality_score": 0,
                "reasons": [f"Malformed career title rejected: {career_name!r}"],
            }

        # Hard rejection: no skills at all
        if not facts.get("skills"):
            return {
                "is_valid": False,
                "quality_score": 0,
                "reasons": ["No skills extracted — cannot build meaningful knowledge"],
            }

        score   = 0
        reasons = []

        # ── 1. Source reliability (max 20 pts) ─────────────────────────
        rel_pts = min(20, int(source_reliability * 0.20))
        score  += rel_pts
        if rel_pts < 10:
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

        # ── 4. Skill count and quality (max 20 pts) ─────────────────────
        skills  = facts.get("skills", [])
        n_skills = len(skills)
        if n_skills > 10:
            score += 20
        elif n_skills >= 6:
            score += 15
        elif n_skills >= 3:
            score += 10
        elif n_skills >= 1:
            score += 5
        # n_skills == 0 already hard-rejected above

        # Penalise if no Required-tier skills are present (low consensus)
        has_required = any(
            (s.get("skill_type") if isinstance(s, dict) else None) == "Required"
            for s in skills
        )
        if not has_required and n_skills > 0:
            score = max(0, score - 5)
            reasons.append("No Required-tier skills — consensus across sources may be low")

        # ── 5. Company count (max 15 pts) ────────────────────────────────
        companies = facts.get("companies", [])
        n_comp    = len(companies)
        if n_comp > 3:
            score += 15
        elif n_comp >= 2:
            score += 10
        elif n_comp >= 1:
            score += 5
        else:
            reasons.append("No recognisable hiring companies found")

        is_valid = score >= 50

        if not is_valid:
            logger.info(
                "KnowledgeValidator: rejected %r  score=%d  reasons=%s",
                career_name, score, reasons,
            )

        return {
            "is_valid":     is_valid,
            "quality_score": min(100, score),
            "reasons":      reasons,
        }
