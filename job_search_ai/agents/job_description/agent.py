"""
Frappe REST entry point.

Call via: POST /api/method/job_search_ai.agents.job_description.api.generate_job_description
"""

from __future__ import annotations

import frappe

from job_search_ai.agents.job_description.job_description_agent import (
    JobDescriptionAgent,
    JobDescriptionAgentError,
)
from job_search_ai.agents.job_description.schemas import JobDescriptionRequest


@frappe.whitelist(allow_guest=True)
def generate_job_description(
    role: str,
    seniority: str | None = None,
    department: str | None = None,
    company_name: str | None = None,
    company_summary: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    must_have_skills: str | list | None = None,
    nice_to_have_skills: str | list | None = None,
):
    def _as_list(val):
        if not val:
            return []
        if isinstance(val, list):
            return val
        return [s.strip() for s in val.split(",") if s.strip()]

    request = JobDescriptionRequest(
        role=role,
        seniority=seniority,
        department=department,
        company_name=company_name,
        company_summary=company_summary,
        location=location,
        employment_type=employment_type,
        must_have_skills=_as_list(must_have_skills),
        nice_to_have_skills=_as_list(nice_to_have_skills),
    )

    try:
        response = JobDescriptionAgent().run(request)
    except JobDescriptionAgentError as exc:
        frappe.throw(str(exc))
        return  # unreachable, keeps type checkers happy

    return {
        "title": response.title,
        "summary": response.summary,
        "responsibilities": response.responsibilities,
        "required_skills": response.required_skills,
        "preferred_skills": response.preferred_skills,
        "qualifications": response.qualifications,
        "employment_type": response.employment_type,
        "location": response.location,
        "markdown": response.to_markdown(),
        "metrics": response.metrics,
    }