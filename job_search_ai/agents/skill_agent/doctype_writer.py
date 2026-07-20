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

    # Map the simplified categories back to the simple doctype fields
    primary = profile.foundation_skills
    advanced = profile.core_domain_skills
    expert = profile.industry_skills + profile.emerging_skills

    def _safe_join(skills: list[str], max_len: int = 140) -> str:
        parts = []
        for s in skills:
            candidate = ", ".join(parts + [s])
            if len(candidate) > max_len:
                break
            parts.append(s)
        if not parts and skills:
            return skills[0][:max_len]
        return ", ".join(parts)

    doc = frappe.get_doc({
        "doctype": "Job Description",
        "job_profile": job_profile,
        "role": profile.role_name,
        "primary_skills": _safe_join(primary),
        "advanced_skills": _safe_join(advanced),
        "expert_skills": _safe_join(expert),
    })
    doc.insert(ignore_permissions=False)
    frappe.db.commit()

    logger.info("SkillAgent: saved Job Description %r for role=%r", doc.name, profile.role_name)
    return doc.name