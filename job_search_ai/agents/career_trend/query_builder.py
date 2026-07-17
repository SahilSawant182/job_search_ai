# -*- coding: utf-8 -*-
"""
QueryBuilder — builds career-centric search queries from a StudentProfile.

V3 Changes
----------
- Generates queries per interest area (up to 2 interests), not just for
  interests[0].  This means the MISS path searches for multiple specific
  career roles, giving the LLM extractor more diverse material to work with.
- Each interest produces 2 queries: a skills query and a demand query.
- Total: up to 4 queries per request (2 interests × 2 queries each).

Do NOT generate queries for:
- Salary / compensation
- Learning roadmaps / courses
- Company hiring lists
- Interview tips
- Certifications
- Resume advice
"""

from __future__ import annotations

import logging

from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.services.knowledge.constants import JOB_SEARCH_DOMAINS

logger = logging.getLogger(__name__)

# Maximum number of interests to query for (cap Tavily usage)
MAX_INTERESTS = 2


class QueryBuilder:
    """
    Builds a list of career-centric search queries from a StudentProfile.

    Usage::

        builder = QueryBuilder()
        queries = builder.build(student_profile)
    """

    def build(self, student: StudentProfile) -> list[str]:
        """
        Generate targeted search queries, one set per student interest.

        Strategy
        --------
        For each interest (up to MAX_INTERESTS):
          Q1 — Required skills for this specific role + job sites
          Q2 — Career demand and hiring trends

        Args:
            student: A fully-populated StudentProfile.

        Returns:
            A list of 2–4 search query strings.
        """
        logger.info(
            "QueryBuilder V3: building queries — "
            "branch=%r  interests=%r  country=%r",
            student.branch,
            student.interests,
            student.country,
        )

        country   = student.country or "India"
        job_sites = " OR ".join(JOB_SEARCH_DOMAINS)

        # Derive career focus areas from interests → skills → branch
        focus_areas = self._derive_focus_areas(student)
        queries: list[str] = []

        for focus in focus_areas[:MAX_INTERESTS]:
            # Q1: What skills are required for this role?
            queries.append(
                f"{focus} required skills job description {job_sites} {country}"
            )
            # Q2: Is this career in demand?
            queries.append(
                f"{focus} career demand hiring trends future growth {country}"
            )

        logger.info("QueryBuilder V3: generated %d queries: %s", len(queries), queries)
        return queries

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _derive_focus_areas(self, student: StudentProfile) -> list[str]:
        """
        Return an ordered list of career focus areas from the student profile.

        Priority:
          1. Student interests (most specific signal)
          2. Dominant skill (proxy for current specialisation)
          3. Branch (broad fallback)
        """
        areas: list[str] = []

        if student.interests:
            for interest in student.interests:
                if interest.strip() and interest.strip() not in areas:
                    areas.append(interest.strip())

        if not areas and student.skills:
            areas.append(student.skills[0].strip())

        if not areas:
            areas.append(student.branch.strip())

        return areas
