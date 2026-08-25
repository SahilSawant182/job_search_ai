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
MAX_INTERESTS = 1


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
          Q1 — Required skills for this specific role + job sites (with branch context)
          Q2 — Career demand and hiring trends

        Branch context is appended to Q1 to disambiguate generic terms.
        For example, "Operations" with branch "Operations Management" stays
        in business/management domain rather than returning DevOps tech results.

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

        # Build a branch context suffix for Q1 disambiguation
        branch_ctx = self._branch_context(student)

        # Derive career focus areas from interests → skills → branch
        focus_areas = self._derive_focus_areas(student)
        queries: list[str] = []

        for focus in focus_areas[:MAX_INTERESTS]:
            # Q1: What skills are required for this role? (include branch context)
            if branch_ctx:
                queries.append(
                    f"{focus} {branch_ctx} required skills job description {job_sites} {country}"
                )
            else:
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

    def _branch_context(self, student: StudentProfile) -> str:
        """
        Return a short domain-disambiguation phrase based on the student's branch.

        This is prepended to Q1 so that generic interest terms (e.g. "Operations")
        are associated with the correct domain ("business management") and not
        pulled towards unrelated tech domains ("DevOps").
        """
        branch_lower = (student.branch or "").lower()
        degree_lower = (student.degree or "").lower()

        _TECH_KW  = {"computer", "software", "it", "information technology", "mca", "cse", "engineering"}
        _BIZ_KW   = {"business", "management", "mba", "bba", "commerce", "marketing", "finance", "operations"}
        _MED_KW   = {"medical", "nursing", "pharma", "health", "clinical", "mbbs", "bsc nursing"}
        _SCI_KW   = {"biology", "chemistry", "physics", "biotechnology", "agriculture", "science"}
        _ARTS_KW  = {"psychology", "sociology", "political", "communication", "journalism", "mass", "arts", "humanities", "english", "literature"}
        _DESIGN_KW = {"design", "animation", "fashion", "fine arts", "architecture"}
        _LEGAL_KW  = {"law", "legal", "llb"}

        combined = branch_lower + " " + degree_lower

        if any(k in combined for k in _TECH_KW):
            return ""  # Tech searches need no disambiguation
        if any(k in combined for k in _BIZ_KW):
            return "business management"
        if any(k in combined for k in _MED_KW):
            return "healthcare medical"
        if any(k in combined for k in _SCI_KW):
            return "science research"
        if any(k in combined for k in _ARTS_KW):
            return "social sciences humanities"
        if any(k in combined for k in _DESIGN_KW):
            return "creative design"
        if any(k in combined for k in _LEGAL_KW):
            return "legal law"

        return ""
