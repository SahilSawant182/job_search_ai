"""
Persists a SkillProfile into the "Job Description" doctype.

ASSUMPTION (verify against your actual "Career Knowledge" doctype):
job_profile resolution looks for a "Career Knowledge" record whose
`career_name` field matches the role. Adjust CAREER_KNOWLEDGE_NAME_FIELD
below if that field is called something else in your schema.
"""

from __future__ import annotations

import logging

import frappe

from job_search_ai.agents.skill_agent.schemas import SkillProfile

logger = logging.getLogger(__name__)

CAREER_KNOWLEDGE_DOCTYPE = "Career Knowledge"
CAREER_KNOWLEDGE_NAME_FIELD = "career_name"   # <-- adjust if your field is named differently


def _resolve_job_profile(role: str) -> str | None:
    """Find an existing Career Knowledge record for this role. Returns its
    `name` (docname) for the Link field, or None if not found."""
    try:
        matches = frappe.get_all(
            CAREER_KNOWLEDGE_DOCTYPE,
            filters={CAREER_KNOWLEDGE_NAME_FIELD: role},
            fields=["name"],
            limit=1,
        )
        if matches:
            return matches[0]["name"]

        # Fall back to a case-insensitive partial match.
        matches = frappe.get_all(
            CAREER_KNOWLEDGE_DOCTYPE,
            filters=[[CAREER_KNOWLEDGE_NAME_FIELD, "like", f"%{role}%"]],
            fields=["name"],
            limit=1,
        )
        if matches:
            return matches[0]["name"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("SkillAgent: could not resolve Career Knowledge for role=%r (%s)", role, exc)

    return None


def save_job_description(profile: SkillProfile) -> str:
    """
    Create a new "Job Description" doc from a SkillProfile.
    Returns the saved doc's name. Does NOT submit it (is_submittable=1,
    but submission should stay a deliberate user/API action).
    """
    job_profile = _resolve_job_profile(profile.role_name)
    if not job_profile:
        logger.warning(
            "SkillAgent: no matching '%s' record for role=%r — saving without job_profile link",
            CAREER_KNOWLEDGE_DOCTYPE, profile.role_name,
        )

    foundation = profile.foundation_skills
    core_domain = profile.core_domain_skills
    industry = profile.industry_skills
    emerging = profile.emerging_skills

    def _safe_join(skills: list[str], max_len: int = 1000) -> str:
        parts = []
        for s in skills:
            candidate = ", ".join(parts + [s])
            if len(candidate) > max_len:
                break
            parts.append(s)
        if not parts and skills:
            return skills[0][:max_len]
        return ", ".join(parts)

    existing_name = frappe.db.get_value("Job Description", {"role": profile.role_name}, "name")
    if existing_name:
        doc = frappe.get_doc("Job Description", existing_name)
        doc.job_profile = job_profile
        doc.foundation_skills = _safe_join(foundation)
        doc.core_domain_skills = _safe_join(core_domain)
        doc.industry_skills = _safe_join(industry)
        doc.emerging_skills = _safe_join(emerging)
        # Populate deprecated columns for backwards compatibility
        doc.primary_skills = _safe_join(foundation)
        doc.advanced_skills = _safe_join(core_domain)
        doc.expert_skills = _safe_join(industry + emerging)
        doc.save(ignore_permissions=False)
        logger.info("SkillAgent: updated Job Description %r for role=%r", doc.name, profile.role_name)
    else:
        doc = frappe.get_doc({
            "doctype": "Job Description",
            "name": profile.role_name,
            "job_profile": job_profile,
            "role": profile.role_name,
            "foundation_skills": _safe_join(foundation),
            "core_domain_skills": _safe_join(core_domain),
            "industry_skills": _safe_join(industry),
            "emerging_skills": _safe_join(emerging),
            # Populate deprecated columns for backwards compatibility
            "primary_skills": _safe_join(foundation),
            "advanced_skills": _safe_join(core_domain),
            "expert_skills": _safe_join(industry + emerging),
        })
        doc.insert(ignore_permissions=False)
        logger.info("SkillAgent: created Job Description %r for role=%r", doc.name, profile.role_name)

    frappe.db.commit()
    return doc.name