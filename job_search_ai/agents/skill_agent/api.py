"""
Call via: POST /api/method/job_search_ai.agents.skill_agent.api.generate_skills
"""

from __future__ import annotations

import frappe
from job_search_ai.agents.skill_agent.schemas import SkillRequest
from job_search_ai.agents.skill_agent.skill_agent import SkillAgent, SkillAgentError


# @frappe.whitelist(allow_guest=True)
# def generate_skills(role: str, seniority: str | None = None, save: int = 1):
#     request = SkillRequest(role=role, seniority=seniority)

#     try:
#         result = SkillAgent().run(request, save_to_doctype=bool(int(save)))
#     except SkillAgentError as exc:
#         frappe.throw(str(exc))
#         return  # unreachable

#     return {
#         "role": result.profile.role_name,
#         "primary_skills": result.profile.primary_skills,
#         "advanced_skills": result.profile.advanced_skills,
#         "expert_skills": result.profile.expert_skills,
#         "source": result.profile.source,
#         "doc_name": result.doc_name,
#         "metrics": result.metrics,
#     }


@frappe.whitelist(allow_guest=True)
def generate_skills(role: str, seniority: str | None = None, save: int = 1):
    request = SkillRequest(role=role, seniority=seniority)

    try:
        result = SkillAgent().run(request, save_to_doctype=bool(int(save)))
    except SkillAgentError as exc:
        frappe.throw(str(exc))
        return  

    # Save only if requested
    job_description = None
    # if int(save):
    #     job_description = save_job_description(
    #         job_profile=role,   # Replace with the actual Job Profile if available
    #         result=result
    #     )

    return {
        "role": result.profile.role_name,
        "foundation_skills": result.profile.foundation_skills,
        "core_domain_skills": result.profile.core_domain_skills,
        "industry_skills": result.profile.industry_skills,
        "emerging_skills": result.profile.emerging_skills,
        "primary_skills": result.profile.foundation_skills,
        "advanced_skills": result.profile.core_domain_skills,
        "expert_skills": result.profile.industry_skills + result.profile.emerging_skills,
        "source": result.profile.source,
        "doc_name": result.doc_name,
        "job_description": job_description,
        "metrics": result.metrics,
    }
@frappe.whitelist(allow_guest=True)
def save_job_description(job_profile, result):
    # Ignore if role already exists
    if frappe.db.exists("Job Description", {"role": result.profile.role_name}):
        return None

    doc = frappe.get_doc({
        "doctype": "Job Description",
        "job_profile": job_profile,
        "role": result.profile.role_name,
        "primary_skills": ", ".join(result.profile.primary_skills),
        "advanced_skills": ", ".join(result.profile.advanced_skills),
        "expert_skills": ", ".join(result.profile.expert_skills),
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name