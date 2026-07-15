"""
QueryBuilder — builds career-centric search queries from a StudentProfile.

Responsibility:
    Generate targeted search queries based on the student's skills and
    interests, NOT their degree branch.  The knowledge base stores careers
    (Frontend Developer, Data Engineer, etc.), not branches (Computer Engineering).
    Queries must target careers so that Tavily results map cleanly onto Career
    Knowledge documents.

Architecture principle:
    Pure deterministic Python. No LLM calls. No network I/O.
"""

from __future__ import annotations

import logging

from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.services.knowledge.constants import (
    JOB_SEARCH_DOMAINS,
    SALARY_SEARCH_DOMAINS,
)

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    Builds a list of career-centric search queries from a StudentProfile.

    Queries target specific career roles and required skills, not broad
    academic branches, so Tavily results can be correctly mapped to
    Career Knowledge documents in the knowledge base.

    Usage::

        builder = QueryBuilder()
        queries = builder.build(student_profile)
    """

    def build(self, student: StudentProfile) -> list[str]:
        """
        Generate career-centric search queries.

        Strategy
        --------
        1. Career role + skills query  — target job platforms
        2. Career role + salary guides — target salary benchmark sites

        Args:
            student: A fully-populated StudentProfile.

        Returns:
            A list containing targeted search query strings.
        """
        logger.info(
            "QueryBuilder: building career-centric queries — "
            "branch=%r  interests=%r  skills=%r  country=%r",
            student.branch,
            student.interests,
            student.skills,
            student.country,
        )

        # Derive the primary career focus from interests > skills > branch
        career_focus = self._infer_career_focus(student)
        country      = student.country or "India"

        job_sites = " OR ".join(JOB_SEARCH_DOMAINS)
        salary_sites = " OR ".join(SALARY_SEARCH_DOMAINS)

        queries: list[str] = [
            # Q1: Skills & requirements on trusted job platforms
            f"{career_focus} skills requirements {job_sites} {country}",

            # Q2: Career path & salary guides on trusted benchmark sites
            f"{career_focus} salary guide career path {salary_sites} {country}",
        ]

        logger.info("QueryBuilder: generated %d queries: %s", len(queries), queries)
        return queries

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_career_focus(self, student: StudentProfile) -> str:
        """
        Infer the most relevant career focus from the student's profile.

        Priority order:
          1. First interest (most explicit signal from student)
          2. Dominant skill cluster
          3. Branch (weakest signal — last resort)
        """
        if student.interests:
            return student.interests[0]

        if student.skills:
            # Return first skill as a direct proxy for career focus without hardcoded mappings
            return student.skills[0]

        # Last resort: return branch as-is (will still produce useful queries)
        return student.branch
