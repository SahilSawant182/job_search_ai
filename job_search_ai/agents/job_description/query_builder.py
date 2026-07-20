from __future__ import annotations

from job_search_ai.agents.job_description.schemas import JobDescriptionRequest


class QueryBuilder:
    """Builds Tavily search queries to research a role for JD generation."""

    def build(self, request: JobDescriptionRequest) -> list[str]:
        role = request.role.strip()
        seniority = f"{request.seniority} " if request.seniority else ""

        queries = [
            f"{seniority}{role} job description responsibilities",
            f"{seniority}{role} required skills qualifications 2026",
            f"{role} typical daily tasks and duties",
        ]
        if request.department:
            queries.append(f"{role} {request.department} team responsibilities")
        return queries