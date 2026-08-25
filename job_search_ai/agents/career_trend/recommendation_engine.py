# -*- coding: utf-8 -*-
"""
RecommendationEngine — deterministic Python ranking logic for recommended careers.

V4 Changes
----------
1. Hard eligibility gate (_is_eligible) — now returns DIRECT_FIT, TRANSITION_FIT,
   or LOW_FIT instead of a boolean.  This eliminates hard rejections for career
   changers (e.g. B.Tech → Finance with strong finance skills/interests).

2. TRANSITION_FIT — degree/branch compatibility is weak but skills + interests
   strongly align.  Candidate is kept; final_score is penalized by 0.15 to
   rank DIRECT_FIT careers above TRANSITION_FIT ones.

3. LOW_FIT — zero degree + zero interest + zero skill overlap.  Hard rejected.

4. Arts/Humanities umbrella added to _score_branch.

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
from enum import Enum
from typing import Any

from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.services.knowledge.constants import (
    RECOMMENDATION_WEIGHTS,
    YEAR_STAGE_POLICY,
)

logger = logging.getLogger(__name__)

# Candidates with a final score below this threshold are dropped entirely.
MIN_FINAL_SCORE = 0.20

# Penalty applied to TRANSITION_FIT candidates so DIRECT_FIT ranks higher.
_TRANSITION_FIT_PENALTY = 0.15


class FitType(str, Enum):
    """Classification of how well a career suits the student's academic background."""
    DIRECT_FIT     = "DIRECT_FIT"      # Degree/branch match or neutral
    TRANSITION_FIT = "TRANSITION_FIT"  # Degree mismatch but strong skill/interest signal
    LOW_FIT        = "LOW_FIT"         # Hard reject — zero overlap across all dimensions


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
            # ── Phase 1: Eligibility classification ───────────────────
            fit_type = self._classify_fit(student, candidate)
            if fit_type == FitType.LOW_FIT:
                logger.info(
                    "RecommendationEngine: LOW_FIT REJECTED %r",
                    getattr(candidate, "career_name", "?"),
                )
                continue

            # ── Phase 2: Multi-dimensional scoring ────────────────────
            seniority_tier = self._get_seniority_tier(candidate)
            skill_score, skill_details = self._score_skills(student, candidate, seniority_tier)
            interest_score = self._score_interests(student, candidate)
            keyword_score  = self._score_keywords(student, candidate)
            degree_score   = self._score_degree(student, candidate)
            branch_score   = self._score_branch(student, candidate)
            year_score     = self._score_year_suitability(student, candidate)

            # Preserve the original semantic weight structure without redistribution.
            # If a career lacks degree/branch constraints, the corresponding scoring helper
            # returns a neutral 0.5 fallback score. This avoids artificial score boosting
            # via weight normalization (missing constraint != positive evidence).
            norm_w = dict(RECOMMENDATION_WEIGHTS)

            final_score = (
                norm_w["skill_match"]        * skill_score
                + norm_w["interest_match"]   * interest_score
                + norm_w["keyword_match"]    * keyword_score
                + norm_w["degree_match"]     * degree_score
                + norm_w["branch_match"]     * branch_score
                + norm_w["year_suitability"] * year_score
            )

            # Apply TRANSITION_FIT ranking penalty so DIRECT_FIT careers rank higher
            if fit_type == FitType.TRANSITION_FIT:
                final_score = max(0.0, final_score - _TRANSITION_FIT_PENALTY)

            # Apply Career-stage/Seniority protections to prevent junior students matching senior/managerial roles
            stage_penalty = 0.0
            if student.year <= 2:
                if seniority_tier == "mid":
                    stage_penalty = 0.15
                elif seniority_tier == "senior":
                    stage_penalty = 0.35
            elif student.year == 3:
                if seniority_tier == "senior":
                    stage_penalty = 0.15
            elif student.year >= 4:
                if seniority_tier == "senior":
                    # For Year 4, if student's year is not explicitly listed in suitable_years, apply a light penalty
                    suitable_years = (getattr(candidate, "suitable_years", "") or "").strip()
                    if suitable_years:
                        years_list = [y.strip() for y in suitable_years.split(",") if y.strip()]
                        if "4" not in years_list:
                            stage_penalty = 0.10

            if stage_penalty > 0.0:
                final_score = max(0.0, final_score - stage_penalty)

            # Generate structured reason codes for transparency
            reason_codes: list[str] = []
            if stage_penalty > 0.0:
                reason_codes.append(f"⚠️ Applied experience/seniority gap penalty for Year {student.year}")
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

            if fit_type == FitType.TRANSITION_FIT:
                reason_codes.append(f"⚡ TRANSITION_FIT — degree mismatch but strong skill/interest signal")

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
                "fit_type":         fit_type.value,
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
    # Phase 1: Eligibility classification (replaces boolean gate)
    # ------------------------------------------------------------------

    def _classify_fit(self, student: StudentProfile, candidate: Any) -> FitType:
        """
        Classify how well the student fits the career.

        DIRECT_FIT     — degree/branch matches or no constraint exists.
        TRANSITION_FIT — degree mismatch, but skill + interest signal is strong.
                         Career is kept with a ranking penalty.
        LOW_FIT        — zero overlap across all dimensions. Hard reject.
        """
        suitable_degrees = (getattr(candidate, "suitable_degrees", "") or "").strip()
        has_degree_constraint = bool(suitable_degrees)
        degree_score = self._score_degree(student, candidate) if has_degree_constraint else 0.5

        interest_score  = self._score_interests(student, candidate)
        seniority_tier  = self._get_seniority_tier(candidate)
        skill_score, _  = self._score_skills(student, candidate, seniority_tier)
        keyword_score   = self._score_keywords(student, candidate)

        # Hard reject: no signal at all
        if interest_score == 0.0 and skill_score == 0.0 and keyword_score == 0.0:
            return FitType.LOW_FIT

        # Degree mismatch but signals are strong → TRANSITION_FIT
        if has_degree_constraint and degree_score == 0.0:
            strong_interest = interest_score >= 0.40
            strong_skill    = skill_score    >= 0.30
            if strong_interest or strong_skill:
                return FitType.TRANSITION_FIT
            return FitType.LOW_FIT  # Degree mismatch + weak signals

        return FitType.DIRECT_FIT

    def _is_eligible(self, student: StudentProfile, candidate: Any) -> bool:
        """Legacy boolean wrapper — kept for call-sites that haven't migrated."""
        return self._classify_fit(student, candidate) != FitType.LOW_FIT

    # ------------------------------------------------------------------
    # Phase 2: Scoring helpers
    # ------------------------------------------------------------------

    def _get_candidate_skills(self, candidate: Any) -> tuple[list[str], list[str]]:
        required_skills = list(getattr(candidate, "required_skills", []) or [])
        preferred_skills = list(getattr(candidate, "preferred_skills", []) or [])
        if not required_skills and not preferred_skills and hasattr(candidate, "skills"):
            raw_skills = getattr(candidate, "skills", []) or []
            for s in raw_skills:
                if isinstance(s, dict):
                    sname = s.get("skill_name")
                    stype = s.get("skill_type") or "Required"
                else:
                    sname = getattr(s, "skill_name", None)
                    stype = getattr(s, "skill_type", "Required")
                if sname:
                    if stype == "Required":
                        required_skills.append(sname)
                    elif stype in ("Preferred", "Advanced"):
                        preferred_skills.append(sname)
        return required_skills, preferred_skills

    def _score_skills(self, student: StudentProfile, candidate: Any, seniority_tier: str = "junior") -> tuple[float, dict]:
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

        required_skills, preferred_skills = self._get_candidate_skills(candidate)

        if not required_skills and not preferred_skills:
            return 0.0, {
                "matched_req": [], "missing_req": [],
                "matched_pref": [], "missing_pref": [],
            }

        def _clean_skill(name: str) -> str:
            return re.sub(r'[^a-z0-9]', '', name.strip().lower())

        student_clean = {_clean_skill(s) for s in (student.skills or []) if s}
        for interest in (student.interests or []):
            student_clean.add(_clean_skill(interest))

        def _is_match(candidate_skill: str) -> bool:
            c_clean = _clean_skill(candidate_skill)
            if not c_clean:
                return False
            for s_clean in student_clean:
                if not s_clean:
                    continue
                if len(s_clean) <= 3 or len(c_clean) <= 3:
                    if s_clean == c_clean:
                        return True
                else:
                    if s_clean in c_clean or c_clean in s_clean:
                        return True
            return False

        matched_req  = [s for s in required_skills  if _is_match(s)]
        missing_req  = [s for s in required_skills  if not _is_match(s)]
        matched_pref = [s for s in preferred_skills if _is_match(s)]
        missing_pref = [s for s in preferred_skills if not _is_match(s)]

        mgmt_keywords = {"management", "strategy", "leadership", "agile", "scrum", "product", "business", "planning", "manager"}
        
        def get_weight(skill_name: str) -> float:
            if seniority_tier == "senior":
                if any(kw in skill_name.lower() for kw in mgmt_keywords):
                    return 3.0
                return 1.0 # purely technical
            return 1.0

        req_matched_wt = sum(get_weight(s) for s in matched_req)
        req_total_wt   = sum(get_weight(s) for s in required_skills)
        req_coverage   = req_matched_wt / req_total_wt if req_total_wt > 0 else 0.0

        pref_matched_wt = sum(get_weight(s) for s in matched_pref)
        pref_total_wt   = sum(get_weight(s) for s in preferred_skills)
        pref_coverage   = pref_matched_wt / pref_total_wt if pref_total_wt > 0 else 0.0

        if req_total_wt > 0 and pref_total_wt == 0:
            skill_score = req_coverage
        elif req_total_wt == 0 and pref_total_wt > 0:
            skill_score = pref_coverage
        else:
            skill_score = 0.70 * req_coverage + 0.30 * pref_coverage

        # Apply configurable missing critical skill penalty if required skills exist, scaled by student's academic year
        from job_search_ai.services.knowledge.constants import CRITICAL_SKILL_PENALTY_WEIGHT
        if required_skills and len(missing_req) > 0:
            missing_ratio = len(missing_req) / len(required_skills)
            year = getattr(student, "year", 4)
            try:
                year_val = int(year)
            except (ValueError, TypeError):
                year_val = 4
            penalty_factor = max(0.0, min(1.0, (year_val - 1) / 3.0))
            effective_penalty = CRITICAL_SKILL_PENALTY_WEIGHT * penalty_factor * missing_ratio
            skill_score = max(0.0, skill_score - effective_penalty)

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

        # Helper to normalize words (singular/plural and stemming suffixes)
        def _normalize_word(w: str) -> str:
            w = w.lower().strip()
            if len(w) > 3 and w.endswith("s"):
                if w.endswith("ies"):
                    w = w[:-3] + "y"
                elif w.endswith("es") and not w.endswith("ces") and not w.endswith("ses"):
                    w = w[:-2]
                else:
                    w = w[:-1]
            suffixes = ("ing", "ed", "er", "or", "ist", "ian", "ment", "al", "ic", "ive", "tion", "ity", "y", "is", "yst", "ship")
            for suffix in suffixes:
                if len(w) > len(suffix) + 2 and w.endswith(suffix):
                    w = w[:-len(suffix)]
                    break
            return w.rstrip("eiy")

        target_words = {_normalize_word(w) for w in re.findall(r'\w+', full_target_str) if len(w) > 1}

        def _is_word_match(w: str, target_words: set[str]) -> bool:
            if w in target_words:
                return True
            for tw in target_words:
                if w in tw or tw in w:
                    return True
                if len(w) >= 4 and len(tw) >= 4 and w[:4] == tw[:4]:
                    return True
            return False

        max_score = 0.0
        for interest in interests_lower:
            words = [w for w in re.findall(r'\w+', interest) if len(w) > 1]
            if not words:
                continue
            norm_words = [_normalize_word(w) for w in words]
            matches = sum(1 for w in norm_words if _is_word_match(w, target_words))
            score = matches / len(words)
            if score > max_score:
                max_score = score

        return min(1.0, max_score)

    def _score_keywords(self, student: StudentProfile, candidate: Any) -> float:
        """
        Keyword match score between normalized student keywords and candidate profile text.
        """
        from job_search_ai.agents.career_trend.input_normalizer import InputNormalizer
        student_kws = InputNormalizer().extract_keywords(student)

        if not student_kws:
            return 0.0

        career_name = (getattr(candidate, "career_name", "") or "").lower()
        r_skills, p_skills = self._get_candidate_skills(candidate)
        req_skills  = " ".join(r_skills).lower()
        pref_skills = " ".join(p_skills).lower()
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

        # Business/Commerce degree umbrella
        biz_synonyms = {"commerce", "business", "administration", "management", "b.com", "bcom", "m.com", "mcom", "bba", "mba", "bms", "finance", "accounting"}
        student_is_biz = any(kw in sd_lower for kw in biz_synonyms)

        # Science degree umbrella (non-engineering)
        science_synonyms = {"science", "b.sc", "bsc", "m.sc", "msc", "biology", "physics", "chemistry", "mathematics"}
        student_is_science = any(kw in sd_lower for kw in science_synonyms) and not student_is_tech

        # Arts/Humanities/Design degree umbrella
        arts_synonyms = {"arts", "humanities", "b.a", "ba", "m.a", "ma", "communication", "design", "b.des", "bdes", "psychology", "sociology", "political science"}
        student_is_arts = any(kw in sd_lower for kw in arts_synonyms)

        for d in degrees:
            candidate_is_tech = any(kw in d for kw in eng_synonyms) or any(kw in d for kw in comp_keywords)
            if student_is_tech and candidate_is_tech:
                return 0.8
            
            candidate_is_biz = any(kw in d for kw in biz_synonyms)
            if student_is_biz and candidate_is_biz:
                return 0.8
                
            candidate_is_science = any(kw in d for kw in science_synonyms) and not any(kw in d for kw in eng_synonyms) and not any(kw in d for kw in comp_keywords)
            if student_is_science and candidate_is_science:
                return 0.8

            candidate_is_arts = any(kw in d for kw in arts_synonyms)
            if student_is_arts and candidate_is_arts:
                return 0.8

        _stop = {"and", "degree", "of", "science", "arts", "bachelor", "master"}
        student_words = {w for w in re.findall(r'\w+', sd_lower) if w not in _stop and len(w) >= 3}
        for d in degrees:
            d_words = {w for w in re.findall(r'\w+', d) if w not in _stop and len(w) >= 3}
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
        biz_marketing_umbrella = {
            "marketing", "business", "administration", "strategy", "management",
            "mba", "finance", "sales", "entrepreneur", "entrepreneurship",
            "commerce", "accounting", "bba", "bcom", "startup", "hospitality"
        }
        student_is_biz = any(kw in sb_lower for kw in biz_marketing_umbrella)

        # Arts / Humanities / Social Sciences / Law umbrella
        arts_humanities_umbrella = {
            "arts", "humanities", "psychology", "sociology", "political",
            "communication", "journalism", "mass", "english", "literature", "media",
            "social work", "history", "philosophy", "law", "legal"
        }
        student_is_arts = any(kw in sb_lower for kw in arts_humanities_umbrella)

        # Science (non-engineering) / Healthcare / Medicine umbrella
        science_umbrella = {
            "biology", "chemistry", "physics", "biotechnology", "agriculture",
            "pharmacy", "nursing", "medical", "environmental", "food technology",
            "clinical", "healthcare", "pharma", "medicine"
        }
        student_is_science = any(kw in sb_lower for kw in science_umbrella)

        for b in branches:
            if student_is_cs  and any(kw in b for kw in cs_it_data_umbrella):
                return 0.8
            if student_is_biz and any(kw in b for kw in biz_marketing_umbrella):
                return 0.8
            if student_is_arts and any(kw in b for kw in arts_humanities_umbrella):
                return 0.8
            if student_is_science and any(kw in b for kw in science_umbrella):
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

    def _get_seniority_tier(self, candidate: Any) -> str:
        """Determine candidate's seniority tier (junior, mid, senior) based on metadata and title keywords."""
        stage = (getattr(candidate, "career_stage", "") or "").strip().lower()
        career_name = (getattr(candidate, "career_name", "") or "").strip().lower()

        # 1. Check metadata first
        if any(term in stage for term in ["manager", "lead", "senior", "director", "head"]):
            return "senior"
        if "mid" in stage:
            return "mid"
        if any(term in stage for term in ["entry", "junior"]):
            return "junior"

        # 2. Fallback to title keywords
        senior_keywords = ["manager", "lead", "director", "architect", "senior", "head", "vp", "chief", "principal"]
        if any(kw in career_name for kw in senior_keywords):
            return "senior"

        mid_keywords = ["specialist", "consultant", "expert"]
        if any(kw in career_name for kw in mid_keywords):
            return "mid"

        junior_keywords = ["junior", "assistant", "associate", "intern", "trainee", "beginner"]
        if any(kw in career_name for kw in junior_keywords):
            return "junior"

        return "junior"  # Safe default fallback
