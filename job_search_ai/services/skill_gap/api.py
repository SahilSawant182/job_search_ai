"""
API Endpoint for Skill Gap Analyzer Service.

Call via:
POST /api/method/job_search_ai.services.skill_gap.api.analyze

Payload example:
{
    "student": "student@example.com",
    "role": "Machine Learning Engineer"
}
or
{
    "student": "student@example.com",
    "job_description": "JD-00001"
}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import frappe
from job_search_ai.services.skill_gap.service import SkillGapService


@frappe.whitelist(allow_guest=True)
def analyze(
    student: Optional[str] = None,
    role: Optional[str] = None,
    job_description: Optional[str] = None,
    readiness_threshold: Optional[float] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    if not student and getattr(frappe, "request", None) and hasattr(frappe.request, "get_json"):
        try:
            body = frappe.request.get_json() or {}
            if isinstance(body, dict):
                student = student or body.get("student")
                role = role or body.get("role")
                job_description = job_description or body.get("job_description")
                if "readiness_threshold" in body and body["readiness_threshold"] is not None:
                    readiness_threshold = float(body["readiness_threshold"])
        except Exception:
            pass

    if not student:
        frappe.throw("Parameter 'student' is required.")

    if not role and not job_description:
        frappe.throw("Either 'role' or 'job_description' must be provided.")

    try:
        service = SkillGapService()
        report = service.get_skill_gap_report(
            student=student,
            role=role,
            job_description=job_description,
            readiness_threshold=float(readiness_threshold) if readiness_threshold is not None else None,
        )
        return report.to_dict()
    except (frappe.ValidationError, frappe.DoesNotExistError) as exc:
        frappe.throw(exc)
    except Exception as exc:
        frappe.log_error(title="Skill Gap Analyzer Error", message=frappe.get_traceback())
        frappe.throw(f"Skill Gap Analyzer failed: {str(exc)}")


