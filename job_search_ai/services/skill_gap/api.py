"""
API Endpoint for Skill Gap Analyzer Service.

Call via:
POST /api/method/job_search_ai.services.skill_gap.api.analyze
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import frappe
from job_search_ai.services.skill_gap.service import SkillGapService


def ensure_skill_exists(skill_name: str) -> None:
    skill_name = skill_name.strip()
    if not skill_name:
        return
    # Check if Skill exists in DB
    if not frappe.db.exists("Skill", skill_name):
        try:
            doc = frappe.get_doc({
                "doctype": "Skill",
                "skill_name": skill_name,
                "skill_category": "Technical",
                "skill_level_schema": "Beginner→Expert"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            pass


def ensure_student_exists(student: str) -> str:
    if frappe.db.exists("Student", student):
        return student
    name = frappe.db.get_value("Student", {"email_id": student}, "name")
    if name:
        return name

    # Auto-create guest student
    colleges = frappe.get_all("College", limit=1)
    college_name = colleges[0].name if colleges else "StrideNex Academy"
    try:
        student_doc = frappe.get_doc({
            "doctype": "Student",
            "first_name": "Guest",
            "last_name": "User",
            "email_id": student if "@" in student else f"{student}@example.com",
            "college": college_name,
            "degree": "Engineering",
            "branch": "Computer Science",
            "year": 1,
            "country": "India"
        })
        student_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return student_doc.name
    except Exception:
        frappe.log_error(title="Auto-creating guest student failed", message=frappe.get_traceback())
        return student


@frappe.whitelist(allow_guest=True)
def analyze(
    student: Optional[str] = None,
    role: Optional[str] = None,
    job_description: Optional[str] = None,
    readiness_threshold: Optional[float] = None,
    career: Optional[str] = None,
    student_skills: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    if getattr(frappe, "request", None) and hasattr(frappe.request, "get_json"):
        try:
            body = frappe.request.get_json() or {}
            if isinstance(body, dict):
                student = student or body.get("student")
                role = role or body.get("role")
                job_description = job_description or body.get("job_description")
                career = career or body.get("career")
                student_skills = student_skills or body.get("student_skills")
                if "readiness_threshold" in body and body["readiness_threshold"] is not None:
                    readiness_threshold = float(body["readiness_threshold"])
        except Exception:
            pass

    if not student:
        student = "guest@example.com"

    resolved_student = ensure_student_exists(student)

    # Sync student skills if provided
    if student_skills is not None:
        # Clear existing skills first
        frappe.db.delete("Student Skill", {"student": resolved_student})

        # Parse skill string
        from job_search_ai.services.skill_gap.normalizer import parse_skill_string
        skills_list = parse_skill_string(student_skills) if isinstance(student_skills, str) else student_skills
        if isinstance(skills_list, list):
            for sk in skills_list:
                sk = sk.strip()
                if not sk:
                    continue
                # Ensure the Skill document exists in the Master DB first to prevent link validation errors
                ensure_skill_exists(sk)

                try:
                    frappe.get_doc({
                        "doctype": "Student Skill",
                        "student": resolved_student,
                        "skill": sk,
                        "current_level": "Intermediate",
                        "ai_verified": 1
                    }).insert(ignore_permissions=True)
                except Exception:
                    pass
            frappe.db.commit()

    career_identifier = career or role or job_description
    if not career_identifier:
        frappe.throw("Either 'career', 'role' or 'job_description' must be provided.")

    try:
        service = SkillGapService()
        report = service.get_skill_gap_report(
            student=resolved_student,
            career=career_identifier,
            readiness_threshold=float(readiness_threshold) if readiness_threshold is not None else None,
        )
        return report.to_dict()
    except (frappe.ValidationError, frappe.DoesNotExistError) as exc:
        frappe.throw(exc)
    except Exception as exc:
        frappe.log_error(title="Skill Gap Analyzer Error", message=frappe.get_traceback())
        frappe.throw(f"Skill Gap Analyzer failed: {str(exc)}")
