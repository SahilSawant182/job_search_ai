"""
Integration test script for Skill Gap Analyzer Service (V2).
Run via:
bench --site devstridenex.quantcloud.in execute job_search_ai.services.skill_gap.test_skill_gap.run_test
"""

import json
import frappe
from job_search_ai.services.skill_gap.api import analyze


def run_test():
    student_id = "v2_test_skill_gap@example.com"

    # Add verified & unverified skills
    skills_data = [
        ("Python Programming", "Intermediate", 1),
        ("Programming Basics", "Advanced", 1),
        ("Statistical Analysis", "Intermediate", 1),
        ("Java", "Beginner", 0),  # Should be ignored (unverified)
    ]

    # Cleanup existing test records
    frappe.db.delete("Student Skill", {"student": student_id})
    frappe.db.delete("Student", {"name": student_id})
    for skill_name, _, _ in skills_data:
        frappe.db.delete("Skill", {"name": skill_name})
    frappe.db.commit()

    # Rebuild embedding index to ensure Qdrant collection is initialized and synced
    from job_search_ai.services.skill_gap.skill_embedding_index import SkillEmbeddingBuilder
    try:
        SkillEmbeddingBuilder().rebuild_all()
    except Exception as exc:
        print(f"Warning: Failed to rebuild embedding index: {exc}")

    # Ensure Skill records exist in DB
    created_skills = []
    for skill_name, _, _ in skills_data:
        if not frappe.db.exists("Skill", skill_name):
            doc = frappe.get_doc({
                "doctype": "Skill",
                "skill_name": skill_name
            })
            doc.insert(ignore_permissions=True)
            created_skills.append(skill_name)

    # Create Test Student
    college_name = frappe.db.get_value("College", {}, "name") or "Default College"
    stu = frappe.get_doc({
        "doctype": "Student",
        "first_name": "Test",
        "last_name": "Student",
        "email_id": student_id,
        "college": college_name
    })
    stu.insert(ignore_permissions=True)

    for skill_name, level, verified in skills_data:
        sk = frappe.get_doc({
            "doctype": "Student Skill",
            "student": student_id,
            "skill": skill_name,
            "current_level": level,
            "ai_verified": verified,
            "self_declared": 1,
            "is_public": 1,
        })
        sk.insert(ignore_permissions=True)

    frappe.db.commit()

    # Execute analyze API
    report = analyze(student=student_id, role="Machine Learning Engineer")

    print("\n================ V2 SKILL GAP REPORT ================")
    print(json.dumps(report, indent=2))
    print("=====================================================\n")

    # Assertions
    assert report["student"] == student_id, f"Expected student {student_id}"
    assert any("Python" in s for s in report["matched_skills"]), "Python should be matched"
    assert "Java" not in report["matched_skills"], "Unverified skill Java must be ignored"
    assert report["verified_skill_count"] == 3, f"Expected 3 verified skills, got {report['verified_skill_count']}"
    assert "matched_skill_count" in report, "Metadata field matched_skill_count missing"
    assert "missing_skill_count" in report, "Metadata field missing_skill_count missing"
    assert "ready_for_job" in report, "Metadata field ready_for_job missing"
    assert "priority_order" in report, "Roadmap field priority_order missing"
    assert isinstance(report["priority_order"], list), "priority_order should be a list"

    # Cleanup
    frappe.db.delete("Student Skill", {"student": student_id})
    frappe.db.delete("Student", {"name": student_id})
    for skill_name in created_skills:
        frappe.db.delete("Skill", {"name": skill_name})
    frappe.db.commit()

    print("✅ V2 INTEGRATION TEST PASSED SUCCESSFULLY!")
