"""
Pure Python Skill Gap Analyzer Engine.

Compares student skills vs required job skills.
Zero Frappe or database dependencies — 100% unit-testable.
Supports proficiency level comparisons, extended metadata, and priority order.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from job_search_ai.services.skill_gap.normalizer import (
    get_skill_key,
    normalize_skill,
)
from job_search_ai.services.skill_gap.schemas import (
    SkillGapReport,
    StudentSkillItem,
)

logger = logging.getLogger(__name__)

# Proficiency Level Numeric Mapping
LEVEL_SCALE: Dict[str, int] = {
    "beginner": 1,
    "intermediate": 2,
    "advanced": 3,
    "expert": 4,
}


class SkillGapAnalyzer:
    """
    Pure Python Skill Gap Analyzer Engine.
    Deterministic skill gap analysis and readiness scoring.
    """

    FOUNDATION_WEIGHT: float = 0.30
    CORE_DOMAIN_WEIGHT: float = 0.40
    INDUSTRY_WEIGHT: float = 0.20
    EMERGING_WEIGHT: float = 0.10

    def analyze(
        self,
        student_identifier: str,
        career_title: str,
        student_skills: List[StudentSkillItem],
        foundation_skills: List[str],
        core_domain_skills: List[str],
        industry_skills: List[str],
        emerging_skills: List[str],
        readiness_threshold: float = 70.0,
        default_required_level: str = "Intermediate",
    ) -> SkillGapReport:
        """
        Compare student skills against job skills deterministically.

        Args:
            student_identifier: Student ID or email string.
            career_title: Target career/role title.
            student_skills: List of verified StudentSkillItem objects.
            foundation_skills: Required foundation skills list.
            core_domain_skills: Required core domain skills list.
            industry_skills: Required industry skills list.
            emerging_skills: Required emerging skills list.
            readiness_threshold: Benchmark percentage score for job readiness.
            default_required_level: Default baseline level required for job skills.

        Returns:
            SkillGapReport structured output.
        """
        # Map student skill keys -> StudentSkillItem
        student_key_map: Dict[str, StudentSkillItem] = {}
        for item in student_skills:
            key = get_skill_key(item.skill)
            if key:
                student_key_map[key] = item

        student_keys: Set[str] = set(student_key_map.keys())

        # Category 1: Foundation Skills
        matched_foundation: List[str] = []
        missing_foundation: List[str] = []
        foundation_score_sum: float = 0.0

        for skill in foundation_skills:
            key = get_skill_key(skill)
            display_name = normalize_skill(skill)
            if key in student_keys:
                matched_foundation.append(display_name)
                match_val = self._evaluate_match_quality(
                    student_key_map[key].current_level, default_required_level
                )
                foundation_score_sum += match_val
            else:
                missing_foundation.append(display_name)

        # Category 2: Core Domain Skills
        matched_core_domain: List[str] = []
        missing_core_domain: List[str] = []
        core_domain_score_sum: float = 0.0

        for skill in core_domain_skills:
            key = get_skill_key(skill)
            display_name = normalize_skill(skill)
            if key in student_keys:
                matched_core_domain.append(display_name)
                match_val = self._evaluate_match_quality(
                    student_key_map[key].current_level, "Advanced"
                )
                core_domain_score_sum += match_val
            else:
                missing_core_domain.append(display_name)

        # Category 3: Industry Skills
        matched_industry: List[str] = []
        missing_industry: List[str] = []
        industry_score_sum: float = 0.0

        for skill in industry_skills:
            key = get_skill_key(skill)
            display_name = normalize_skill(skill)
            if key in student_keys:
                matched_industry.append(display_name)
                match_val = self._evaluate_match_quality(
                    student_key_map[key].current_level, "Expert"
                )
                industry_score_sum += match_val
            else:
                missing_industry.append(display_name)

        # Category 4: Emerging Skills
        matched_emerging: List[str] = []
        missing_emerging: List[str] = []
        emerging_score_sum: float = 0.0

        for skill in emerging_skills:
            key = get_skill_key(skill)
            display_name = normalize_skill(skill)
            if key in student_keys:
                matched_emerging.append(display_name)
                match_val = self._evaluate_match_quality(
                    student_key_map[key].current_level, "Advanced"
                )
                emerging_score_sum += match_val
            else:
                missing_emerging.append(display_name)

        # Deduplicated Matched Skills List
        matched_skills_set: Set[str] = set()
        matched_skills: List[str] = []
        for skill_name in matched_foundation + matched_core_domain + matched_industry + matched_emerging:
            if skill_name not in matched_skills_set:
                matched_skills_set.add(skill_name)
                matched_skills.append(skill_name)

        # Construct Priority Order for Roadmap Agent
        # Foundational (Missing Foundation) -> Intermediate (Missing Core Domain) -> Advanced (Missing Industry) -> Emerging
        priority_order_set: Set[str] = set()
        priority_order: List[str] = []
        for skill_name in missing_foundation + missing_core_domain + missing_industry + missing_emerging:
            if skill_name not in priority_order_set:
                priority_order_set.add(skill_name)
                priority_order.append(skill_name)

        # Total Skill Counts
        all_required_keys: Set[str] = set()
        for skill_list in (foundation_skills, core_domain_skills, industry_skills, emerging_skills):
            for skill in skill_list:
                key = get_skill_key(skill)
                if key:
                    all_required_keys.add(key)
        
        verified_skill_count = len(student_skills)
        required_skill_count = len(all_required_keys)
        matched_skill_count = len(matched_skills)
        missing_skill_count = len(priority_order)

        # Readiness Score Calculation with Level Support
        readiness_score = self._calculate_readiness_score(
            foundation_score_sum,
            len(foundation_skills),
            core_domain_score_sum,
            len(core_domain_skills),
            industry_score_sum,
            len(industry_skills),
            emerging_score_sum,
            len(emerging_skills),
        )

        ready_for_job = readiness_score >= readiness_threshold

        return SkillGapReport(
            student=student_identifier,
            career=career_title,
            matched_skills=matched_skills,
            missing_foundation=missing_foundation,
            missing_core_domain=missing_core_domain,
            missing_industry=missing_industry,
            missing_emerging=missing_emerging,
            verified_skill_count=verified_skill_count,
            required_skill_count=required_skill_count,
            matched_skill_count=matched_skill_count,
            missing_skill_count=missing_skill_count,
            readiness_score=readiness_score,
            ready_for_job=ready_for_job,
            priority_order=priority_order,
        )

    def _evaluate_match_quality(
        self, student_level: str, required_level: str
    ) -> float:
        """
        Evaluate match quality factor based on proficiency levels.
        - Exact/Higher level match: 1.0 (Full Match)
        - Partial level match: student_level / required_level (Partial Match)
        """
        stu_val = LEVEL_SCALE.get(str(student_level).strip().lower(), 2)
        req_val = LEVEL_SCALE.get(str(required_level).strip().lower(), 2)

        if stu_val >= req_val:
            return 1.0
        
        # Partial match ratio (e.g. Intermediate (2) for Advanced (3) -> 0.67 match)
        return max(0.5, round(stu_val / float(req_val), 2))

    def _calculate_readiness_score(
        self,
        foundation_score_sum: float,
        total_foundation: int,
        core_domain_score_sum: float,
        total_core_domain: int,
        industry_score_sum: float,
        total_industry: int,
        emerging_score_sum: float,
        total_emerging: int,
    ) -> float:
        """
        Calculate weighted readiness score.
        Target weights are: Foundation: 30%, Core Domain: 40%, Industry: 20%, Emerging: 10%.
        If a category has no required skills, its weight is dynamically redistributed.
        """
        if total_foundation == 0 and total_core_domain == 0 and total_industry == 0 and total_emerging == 0:
            return 100.0

        total_weight = 0.0
        weighted_score_sum = 0.0

        if total_foundation > 0:
            f_pct = (foundation_score_sum / float(total_foundation) * 100.0)
            weighted_score_sum += f_pct * self.FOUNDATION_WEIGHT
            total_weight += self.FOUNDATION_WEIGHT

        if total_core_domain > 0:
            c_pct = (core_domain_score_sum / float(total_core_domain) * 100.0)
            weighted_score_sum += c_pct * self.CORE_DOMAIN_WEIGHT
            total_weight += self.CORE_DOMAIN_WEIGHT

        if total_industry > 0:
            i_pct = (industry_score_sum / float(total_industry) * 100.0)
            weighted_score_sum += i_pct * self.INDUSTRY_WEIGHT
            total_weight += self.INDUSTRY_WEIGHT

        if total_emerging > 0:
            em_pct = (emerging_score_sum / float(total_emerging) * 100.0)
            weighted_score_sum += em_pct * self.EMERGING_WEIGHT
            total_weight += self.EMERGING_WEIGHT

        score = weighted_score_sum / total_weight if total_weight > 0 else 0.0
        score = max(0.0, min(100.0, score))
        return round(score, 1)
