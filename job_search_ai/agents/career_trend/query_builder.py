"""
QueryBuilder — builds structured natural search queries without hardcoded brands.

Responsibility:
    Generate exactly 4 natural and diverse search queries based on the StudentProfile.
    These queries avoid hardcoded organization names to retrieve unbiased
    and high-quality evidence from across the web.
"""

from __future__ import annotations

import logging

from job_search_ai.agents.career_trend.schemas import StudentProfile

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    Builds a list of 4 natural search queries tailored to a StudentProfile.

    Usage::

        builder = QueryBuilder()
        queries = builder.build(student_profile)
    """

    def build(self, student: StudentProfile) -> list[str]:
        """
        Generate natural search queries to find emerging trends.

        Args:
            student: A fully-populated StudentProfile.

        Returns:
            A list containing exactly 4 search query strings.
        """
        logger.info(
            "Building natural query strategies for branch=%r, country=%r",
            student.branch,
            student.country,
        )

        # Diverse base templates
        queries: list[str] = [
            f"Future careers in {student.branch} {student.country}",
            f"Emerging technologies in {student.branch}",
            f"Top skills for {student.branch} professionals",
        ]

        # Fourth query: Interest-specific or default AI trends
        if student.interests:
            interest = student.interests[0]
            queries.append(f"{interest} careers in {student.branch}")
        else:
            queries.append(f"AI careers in {student.branch}")

        logger.debug("Generated 4 natural query strategies: %s", queries)
        return queries
