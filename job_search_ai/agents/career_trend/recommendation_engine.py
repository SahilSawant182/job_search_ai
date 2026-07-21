# -*- coding: utf-8 -*-
"""
RecommendationEngine — deterministic Python ranking logic for recommended careers.

V3 Changes
----------
1. Hard eligibility gate (_is_eligible) — rejects candidates with zero degree
   or branch match before scoring.  An MBA student will NEVER receive a
   "Backend Developer" recommendation that requires only Engineering degrees.

2. Minimum final score threshold — candidates scoring below MIN_FINAL_SCORE
   are excluded from the output even if they pass the eligibility gate.

Scoring weights:
  - Skill Match:      0.40
  - Interest Match:   0.25  (increased — this is the strongest user signal)
  - Year Suitability: 0.15
  - Degree Match:     0.10
  - Branch Match:     0.05
  - Market Demand:    0.05
"""

from __future__ import annotations

import logging
import re
from typing import Any

from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.services.knowledge.constants import (
    RECOMMENDATION_WEIGHTS,
    YEAR_STAGE_POLICY,
)

logger = logging.getLogger(__name__)

# Candidates with a final score below this threshold are dropped entirely.
# This prevents low-confidence mismatches reaching the LLM.
MIN_FINAL_SCORE = 0.20


class ScoredCareer:
    """Carries a candidate career record along with its computed scores and reason codes."""

    def __init__(
        self,
        candidate: Any,
        final_score: float,
        scores: dict[str, float],
        matched_required_skills: list[str],
        missing_required_skills: list[str],
        matched_preferred_skills: list[str],
        missing_preferred_skills: list[str],
        reason_codes: list[str] | None = None,
    ) -> None:
        self.candidate = candidate
        self.final_score = final_score
        self.scores = scores
        self.matched_required_skills = matched_required_skills
        self.missing_required_skills = missing_required_skills
        self.matched_preferred_skills = matched_preferred_skills
        self.missing_preferred_skills = missing_preferred_skills
        self.reason_codes = reason_codes or []


class RecommendationEngine:
    """
    Evaluates, ranks, and filters candidate careers for a StudentProfile.

    The engine runs in two phases:
      1. Hard eligibility gate  — immediately rejects clearly unsuitable careers.
      2. Multi-dimensional score — ranks remaining eligible careers with dynamic weight normalization.
    """

    def rank(
        self,
        student: StudentProfile,
        candidates: list[Any],
    ) -> list[ScoredCareer]:
        """
        Score and rank candidate careers with dynamic weight normalization and reason codes.
        """
        logger.info(
            "RecommendationEngine: ranking %d candidates", len(candidates)
        )

        scored_candidates: list[ScoredCareer] = []

        for candidate in candidates:
            # ── Phase 1: Hard eligibility gate ────────────────────────
            if not self._is_eligible(student, candidate):
                logger.info(
                    "RecommendationEngine: REJECTED %r — failed eligibility gate",
                    getattr(candidate, "career_name", "?"),
                )
                continue

            # ── Phase 2: Multi-dimensional scoring ────────────────────
            skill_score, skill_details = self._score_skills(student, candidate)
            interest_score = self._score_interests(student, candidate)
            keyword_score  = self._score_keywords(student, candidate)
            degree_score   = self._score_degree(student, candidate)
            branch_score   = self._score_branch(student, candidate)
            year_score     = self._score_year_suitability(student, candidate)

            # Dynamic Weight Normalization
            # If candidate/student has no degree constraint, unconstrain degree/branch weights
            w = dict(RECOMMENDATION_WEIGHTS)
            suitable_degrees = (getattr(candidate, "suitable_degrees", "") or "").strip()
            if not suitable_degrees:
                # Re-distribute degree weight onto skills & interests
                w["degree_match"] = 0.0
                w["branch_match"] = 0.0

            total_weight = sum(w.values())
            if total_weight > 0:
                norm_w = {k: v / total_weight for k, v in w.items()}
            else:
                norm_w = w

            final_score = (
                norm_w["skill_match"]      * skill_score
                + norm_w["interest_match"] * interest_score
                + norm_w["keyword_match"]  * keyword_score
                + norm_w["degree_match"]   * degree_score
                + norm_w["branch_match"]   * branch_score
                + norm_w["year_suitability"] * year_score
            )

            # Generate structured reason codes for transparency
            reason_codes: list[str] = []
            career_name = getattr(candidate, "career_name", "") or ""

            if interest_score > 0.0:
                reason_codes.append(f"✓ Interest matched student focus/shorthand ({int(interest_score * 100)}%)")
            if skill_details["matched_req"]:
                reason_codes.append(f"✓ Matched required skills: {', '.join(skill_details['matched_req'])}")
            if skill_details["matched_pref"]:
                reason_codes.append(f"✓ Matched preferred skills: {', '.join(skill_details['matched_pref'])}")
            if keyword_score > 0.0:
                reason_codes.append(f"✓ Domain keyword overlap ({int(keyword_score * 100)}%)")
            if degree_score >= 0.8:
                reason_codes.append(f"✓ Academic degree compatible ({student.degree})")
            if branch_score >= 0.8:
                reason_codes.append(f"✓ Branch domain aligned ({student.branch})")

            if final_score < MIN_FINAL_SCORE:
                logger.info(
                    "RecommendationEngine: DROPPED %r — score=%.4f < %.2f",
                    career_name, final_score, MIN_FINAL_SCORE,
                )
                continue

            scores = {
                "skill_match":      round(skill_score, 4),
                "interest_match":   round(interest_score, 4),
                "keyword_match":    round(keyword_score, 4),
                "degree_match":     round(degree_score, 4),
                "branch_match":     round(branch_score, 4),
                "year_suitability": round(year_score, 4),
            }

            scored_candidates.append(
                ScoredCareer(
                    candidate=candidate,
                    final_score=round(final_score, 4),
                    scores=scores,
                    matched_required_skills=skill_details["matched_req"],
                    missing_required_skills=skill_details["missing_req"],
                    matched_preferred_skills=skill_details["matched_pref"],
                    missing_preferred_skills=skill_details["missing_pref"],
                    reason_codes=reason_codes,
                )
            )

        scored_candidates.sort(key=lambda x: x.final_score, reverse=True)

        for sc in scored_candidates:
            logger.info(
                "Scored: %s | %.4f | %s",
                sc.candidate.career_name, sc.final_score, sc.scores,
            )

        return scored_candidates

    # ------------------------------------------------------------------
    # Phase 1: Hard Eligibility Gate
    # ------------------------------------------------------------------

    def _is_eligible(self, student: StudentProfile, candidate: Any) -> bool:
        """
        Hard eligibility gate.

        Returns False if the career is *clearly* unsuitable for the
        student's degree, or has zero interest + skill + keyword overlap.
        """
        suitable_degrees = (getattr(candidate, "suitable_degrees", "") or "").strip()
        if suitable_degrees:
            degree_score = self._score_degree(student, candidate)
            if degree_score == 0.0:
                return False  # Zero degree overlap — hard reject

        # Reject careers with absolutely zero interest match, zero skill match, and zero keyword match
        interest_score = self._score_interests(student, candidate)
        skill_score, _ = self._score_skills(student, candidate)
        keyword_score  = self._score_keywords(student, candidate)

        if interest_score == 0.0 and skill_score == 0.0 and keyword_score == 0.0:
            return False

        return True

    # ------------------------------------------------------------------
    # Phase 2: Scoring helpers
    # ------------------------------------------------------------------

    def _score_skills(self, student: StudentProfile, candidate: Any) -> tuple[float, dict]:
        """
        Skill match score.
        Weights required skills at 0.70, preferred at 0.30.
        If no student skills or no candidate skills, returns 0.0.
        """
        if not student.skills:
            return 0.0, {
                "matched_req": [], "missing_req": [],
                "matched_pref": [], "missing_pref": [],
            }

        required_skills  = getattr(candidate, "required_skills",  []) or []
        preferred_skills = getattr(candidate, "preferred_skills", []) or []

        if not required_skills and not preferred_skills:
            return 0.0, {
                "matched_req": [], "missing_req": [],
                "matched_pref": [], "missing_pref": [],
            }

        student_lower = {s.strip().lower() for s in student.skills}

        matched_req  = [s for s in required_skills  if s.strip().lower() in student_lower]
        missing_req  = [s for s in required_skills  if s.strip().lower() not in student_lower]
        matched_pref = [s for s in preferred_skills if s.strip().lower() in student_lower]
        missing_pref = [s for s in preferred_skills if s.strip().lower() not in student_lower]

        req_coverage  = len(matched_req)  / len(required_skills)  if required_skills  else 0.0
        pref_coverage = len(matched_pref) / len(preferred_skills) if preferred_skills else 0.0

        skill_score = 0.70 * req_coverage + 0.30 * pref_coverage

        # Apply configurable missing critical skill penalty if required skills exist
        from job_search_ai.services.knowledge.constants import CRITICAL_SKILL_PENALTY_WEIGHT
        if required_skills and len(missing_req) > 0:
            missing_ratio = len(missing_req) / len(required_skills)
            skill_score = max(0.0, skill_score - (CRITICAL_SKILL_PENALTY_WEIGHT * missing_ratio))

        return skill_score, {
            "matched_req": matched_req, "missing_req": missing_req,
            "matched_pref": matched_pref, "missing_pref": missing_pref,
        }

    def _score_interests(self, student: StudentProfile, candidate: Any) -> float:
        """
        Interest match using word-level tokenisation against career name and aliases.
        """
        if not student.interests:
            return 0.0

        career_name = (getattr(candidate, "career_name", "") or "").lower()
        raw_aliases = getattr(candidate, "aliases", []) or []
        if isinstance(raw_aliases, str):
            aliases = [a.strip().lower() for a in raw_aliases.split(",") if a.strip()]
        else:
            aliases = [str(a).strip().lower() for a in raw_aliases if a]

        target_texts = [career_name] + aliases
        full_target_str = " ".join(target_texts)

        if not full_target_str.strip():
            return 0.0

        interests_lower = [i.strip().lower() for i in student.interests]

        # Full-phrase check first (highest signal)
        for interest in interests_lower:
            if interest and interest in full_target_str:
                return 1.0

        # Word-level tokenisation
        expanded: set[str] = set()
        for interest in interests_lower:
            words = [w for w in re.findall(r'\w+', interest) if len(w) > 2]
            expanded.update(words)

        if not expanded:
            return 0.0

        matches = sum(1 for token in expanded if token in full_target_str)
        return min(1.0, matches / max(1, len(expanded)))

    def _score_keywords(self, student: StudentProfile, candidate: Any) -> float:
        """
        Keyword match score between normalized student keywords and candidate profile text.
        """
        from job_search_ai.agents.career_trend.input_normalizer import InputNormalizer
        student_kws = InputNormalizer().extract_keywords(student)

        if not student_kws:
            return 0.0

        career_name = (getattr(candidate, "career_name", "") or "").lower()
        req_skills  = " ".join(getattr(candidate, "required_skills", []) or []).lower()
        pref_skills = " ".join(getattr(candidate, "preferred_skills", []) or []).lower()
        raw_aliases = getattr(candidate, "aliases", []) or []
        aliases_str = " ".join(raw_aliases).lower() if isinstance(raw_aliases, list) else str(raw_aliases).lower()

        candidate_corpus = f"{career_name} {aliases_str} {req_skills} {pref_skills}"

        matches = sum(1 for kw in student_kws if kw in candidate_corpus)
        return min(1.0, matches / max(1, len(student_kws)))

    def _score_degree(self, student: StudentProfile, candidate: Any) -> float:
        """
        Degree match score.
        1.0 = exact match, 0.8 = keyword overlap / tech degree compatibility, 0.5 = no info, 0.0 = mismatch.
        """
        suitable_degrees = (getattr(candidate, "suitable_degrees", "") or "").strip()
        if not suitable_degrees:
            return 0.5  # No constraint — neutral

        degrees = [d.strip().lower() for d in suitable_degrees.split(",") if d.strip()]
        sd_lower = student.degree.strip().lower()

        if sd_lower in degrees:
            return 1.0

        # Technical/Engineering degree umbrella
        eng_synonyms = {"engineering", "technology", "tech", "b.tech", "btech", "m.tech", "mtech", "b.e", "b.e.", "m.e", "m.e."}
        comp_keywords = {"computer", "cs", "it", "information", "mca", "science"}
        student_is_tech = any(kw in sd_lower for kw in eng_synonyms) or any(kw in sd_lower for kw in comp_keywords)

        for d in degrees:
            candidate_is_tech = any(kw in d for kw in eng_synonyms) or any(kw in d for kw in comp_keywords)
            if student_is_tech and candidate_is_tech:
                return 0.8

        student_words = set(re.findall(r'\w+', sd_lower)) - {"and", "degree", "of", "science", "arts", "bachelor", "master"}
        for d in degrees:
            d_words = set(re.findall(r'\w+', d)) - {"and", "degree", "of", "science", "arts", "bachelor", "master"}
            if student_words & d_words:
                return 0.8

        return 0.0  # Explicit degree constraint — student doesn't match any

    def _score_branch(self, student: StudentProfile, candidate: Any) -> float:
        """Branch match score."""
        suitable_branches = (
            getattr(candidate, "suitable_branches", "")
            or getattr(candidate, "applicable_branches", "")
            or ""
        ).strip()
        if not suitable_branches:
            return 0.5

        branches = [b.strip().lower() for b in suitable_branches.split(",") if b.strip()]
        sb_lower = student.branch.strip().lower()

        if sb_lower in branches:
            return 1.0

        # Umbrella keywords for Computer Science / IT / Software / Data Science / AI / ML
        cs_it_data_umbrella = {
            "computer", "cs", "cse", "it", "information", "software", "web", "systems",
            "network", "programming", "development", "data", "ai", "ml", "intelligence",
            "machine", "analytics", "database", "cloud", "devops", "security"
        }
        student_is_cs = any(kw in sb_lower for kw in cs_it_data_umbrella)

        # Umbrella for business/marketing
        biz_marketing_umbrella = {"marketing", "business", "administration", "strategy", "management", "mba", "finance", "sales"}
        student_is_biz = any(kw in sb_lower for kw in biz_marketing_umbrella)

        for b in branches:
            # CS/IT/Data umbrella match
            if student_is_cs and any(kw in b for kw in cs_it_data_umbrella):
                return 0.8
            # Business/Marketing umbrella match
            if student_is_biz and any(kw in b for kw in biz_marketing_umbrella):
                return 0.8

        student_words = set(re.findall(r'\w+', sb_lower)) - {"and", "engineering", "technology", "science"}
        for b in branches:
            b_words = set(re.findall(r'\w+', b)) - {"and", "engineering", "technology", "science"}
            if student_words & b_words:
                return 0.8

        return 0.0

    def _score_year_suitability(self, student: StudentProfile, candidate: Any) -> float:
        """Year suitability based on academic year and career stage / suitable_years."""
        stage = (getattr(candidate, "career_stage", "") or "").strip()
        policy = YEAR_STAGE_POLICY.get(student.year, YEAR_STAGE_POLICY.get(3, {}))
        stage_score = policy.get(stage, 0.5) if stage else 0.5

        # Boost if student's year is explicitly in suitable_years
        suitable_years = (getattr(candidate, "suitable_years", "") or "").strip()
        if suitable_years:
            years_list = [y.strip() for y in suitable_years.split(",") if y.strip()]
            if str(student.year) in years_list:
                return max(stage_score, 1.0)

        return stage_score

    def _score_demand(self, candidate: Any) -> float:
        """Map demand string to a score."""
        demand = (getattr(candidate, "future_demand", "") or "").strip().lower()
        return {
            "very high": 1.0,
            "high":      0.8,
            "medium":    0.5,
            "moderate":  0.5,
            "low":       0.2,
        }.get(demand, 0.5)
