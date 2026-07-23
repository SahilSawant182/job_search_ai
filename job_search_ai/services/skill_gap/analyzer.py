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

    PRIMARY_WEIGHT: float = 0.40
    ADVANCED_WEIGHT: float = 0.40
    EXPERT_WEIGHT: float = 0.20

    def analyze(
        self,
        student_identifier: str,
        career_title: str,
        student_skills: List[StudentSkillItem],
        primary_skills: List[str],
        advanced_skills: List[str],
        expert_skills: List[str],
        readiness_threshold: float = 70.0,
        default_required_level: str = "Intermediate",
    ) -> SkillGapReport:
        """
        Compare student skills against job skills deterministically.

        Args:
            student_identifier: Student ID or email string.
            career_title: Target career/role title.
            student_skills: List of verified StudentSkillItem objects.
            primary_skills: Required primary skills list.
            advanced_skills: Required advanced skills list.
            expert_skills: Required expert skills list.
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

        # Category 1: Primary Skills
        matched_primary: List[str] = []
        missing_primary: List[str] = []
        primary_score_sum: float = 0.0

        for skill in primary_skills:
            key = get_skill_key(skill)
            display_name = normalize_skill(skill)
            if key in student_keys:
                matched_primary.append(display_name)
                match_val = self._evaluate_match_quality(
                    student_key_map[key].current_level, default_required_level
                )
                primary_score_sum += match_val
            else:
                missing_primary.append(display_name)

        # Category 2: Advanced Skills
        matched_advanced: List[str] = []
        missing_advanced: List[str] = []
        advanced_score_sum: float = 0.0

        for skill in advanced_skills:
            key = get_skill_key(skill)
            display_name = normalize_skill(skill)
            if key in student_keys:
                matched_advanced.append(display_name)
                match_val = self._evaluate_match_quality(
                    student_key_map[key].current_level, "Advanced"
                )
                advanced_score_sum += match_val
            else:
                missing_advanced.append(display_name)

        # Category 3: Expert Skills
        matched_expert: List[str] = []
        missing_expert: List[str] = []
        expert_score_sum: float = 0.0

        for skill in expert_skills:
            key = get_skill_key(skill)
            display_name = normalize_skill(skill)
            if key in student_keys:
                matched_expert.append(display_name)
                match_val = self._evaluate_match_quality(
                    student_key_map[key].current_level, "Expert"
                )
                expert_score_sum += match_val
            else:
                missing_expert.append(display_name)

        # Deduplicated Matched Skills List
        matched_skills_set: Set[str] = set()
        matched_skills: List[str] = []
        for skill_name in matched_primary + matched_advanced + matched_expert:
            if skill_name not in matched_skills_set:
                matched_skills_set.add(skill_name)
                matched_skills.append(skill_name)

        # Construct Priority Order for Roadmap Agent
        # Foundational (Missing Primary) -> Intermediate (Missing Advanced) -> Advanced (Missing Expert)
        priority_order_set: Set[str] = set()
        priority_order: List[str] = []
        for skill_name in missing_primary + missing_advanced + missing_expert:
            if skill_name not in priority_order_set:
                priority_order_set.add(skill_name)
                priority_order.append(skill_name)

        # Total Skill Counts
        all_required_keys: Set[str] = set()
        for skill_list in (primary_skills, advanced_skills, expert_skills):
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
            primary_score_sum,
            len(primary_skills),
            advanced_score_sum,
            len(advanced_skills),
            expert_score_sum,
            len(expert_skills),
        )

        ready_for_job = readiness_score >= readiness_threshold

        return SkillGapReport(
            student=student_identifier,
            career=career_title,
            matched_skills=matched_skills,
            missing_primary=missing_primary,
            missing_advanced=missing_advanced,
            missing_expert=missing_expert,
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
        primary_score_sum: float,
        total_primary: int,
        advanced_score_sum: float,
        total_advanced: int,
        expert_score_sum: float,
        total_expert: int,
    ) -> float:
        """
        Calculate weighted readiness score.
        Target weights are: Primary: 40%, Advanced: 40%, Expert: 20%.
        If a category has no required skills, its weight is dynamically redistributed.
        """
        if total_primary == 0 and total_advanced == 0 and total_expert == 0:
            return 100.0

        total_weight = 0.0
        weighted_score_sum = 0.0

        if total_primary > 0:
            p_pct = (primary_score_sum / float(total_primary) * 100.0)
            weighted_score_sum += p_pct * self.PRIMARY_WEIGHT
            total_weight += self.PRIMARY_WEIGHT

        if total_advanced > 0:
            a_pct = (advanced_score_sum / float(total_advanced) * 100.0)
            weighted_score_sum += a_pct * self.ADVANCED_WEIGHT
            total_weight += self.ADVANCED_WEIGHT

        if total_expert > 0:
            e_pct = (expert_score_sum / float(total_expert) * 100.0)
            weighted_score_sum += e_pct * self.EXPERT_WEIGHT
            total_weight += self.EXPERT_WEIGHT

        score = weighted_score_sum / total_weight if total_weight > 0 else 0.0
        score = max(0.0, min(100.0, score))
        return round(score, 1)
