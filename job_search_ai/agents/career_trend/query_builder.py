"""
QueryBuilder — builds career-centric search queries from a StudentProfile.

Responsibility:
    Generate 4 targeted search queries based on the student's skills and
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

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    Builds a list of 4 career-centric search queries from a StudentProfile.

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
        1. Career role + skills query  — most specific, highest recall
        2. Career role + country       — local market data
        3. Skills demand trends        — skills-focused market intelligence
        4. Career path + year-context  — placement-readiness perspective

        Args:
            student: A fully-populated StudentProfile.

        Returns:
            A list containing exactly 4 search query strings.
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
        skills_str   = ", ".join(student.skills[:4]) if student.skills else student.branch
        country      = student.country or "India"

        queries: list[str] = [
            # Q1: Career role + skills — most important, highest signal-to-noise
            f"{career_focus} jobs skills requirements {country} 2025",

            # Q2: Career role + country — local hiring market
            f"{career_focus} career path salary hiring companies {country}",

            # Q3: Skills demand — what the market is paying for
            f"In-demand skills for {career_focus} developers engineers {country}",

            # Q4: Year-context — placement readiness
            self._year_context_query(student, career_focus, country),
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
            # Use skill cluster heuristics to derive a career focus
            skills_lower = [s.lower() for s in student.skills]
            if any(s in skills_lower for s in ["react", "vue", "angular", "html", "css", "javascript", "frontend"]):
                return "Frontend Developer"
            if any(s in skills_lower for s in ["node", "express", "django", "flask", "spring", "backend"]):
                return "Backend Developer"
            if any(s in skills_lower for s in ["react native", "flutter", "android", "ios", "mobile"]):
                return "Mobile Developer"
            if any(s in skills_lower for s in ["aws", "azure", "gcp", "kubernetes", "docker", "devops"]):
                return "DevOps Cloud Engineer"
            if any(s in skills_lower for s in ["python", "tensorflow", "pytorch", "ml", "machine learning", "data"]):
                return "Data Scientist Machine Learning"
            if any(s in skills_lower for s in ["sql", "tableau", "power bi", "analytics"]):
                return "Data Analyst"
            if any(s in skills_lower for s in ["figma", "ui", "ux", "design"]):
                return "UI UX Designer"
            if any(s in skills_lower for s in ["java", "c++", "c#", ".net"]):
                return "Software Engineer"
            # Return first skill as a proxy
            return student.skills[0]

        # Last resort: return branch as-is (will still produce useful queries)
        return student.branch

    def _year_context_query(
        self,
        student: StudentProfile,
        career_focus: str,
        country: str,
    ) -> str:
        """Build a year-aware query for placement-readiness intelligence."""
        year = student.year
        if year >= 4:
            return f"Entry level {career_focus} jobs freshers placement {country} 2025"
        elif year == 3:
            return f"{career_focus} internship placement preparation {country}"
        elif year == 2:
            return f"{career_focus} career roadmap skills to learn {country}"
        else:
            return f"Future scope {career_focus} technology trends {country}"
