import frappe
import time
from job_search_ai.services.skill_gap.service import SkillGapService
from unittest.mock import patch

def test_performance():
    student_id = "test_val_error@example.com"
    college_name = frappe.db.get_value("College", {}, "name") or "Default College"
    
    # Setup test student if not exists
    if not frappe.db.exists("Student", student_id):
        stu = frappe.get_doc({
            "doctype": "Student",
            "first_name": "Test",
            "last_name": "Student",
            "email_id": student_id,
            "college": college_name
        })
        stu.insert(ignore_permissions=True)
        frappe.db.commit()

    # Clear student skills to have a clean slate
    frappe.db.delete("Student Skill", {"student": student_id})
    frappe.db.commit()
    
    # Add one student skill
    doc = frappe.get_doc({
        "doctype": "Student Skill",
        "student": student_id,
        "skill": "Python",
        "current_level": "Intermediate",
        "ai_verified": 1
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    career_profile = {
        "role_name": "Machine Learning Engineer",
        "foundation_skills": ["Python", "Git"],
        "core_domain_skills": ["Machine Learning", "Neural Networks"],
        "industry_skills": ["AWS"],
        "emerging_skills": ["Generative AI"]
    }

    # We will spy on requests.post to ensure no LLM endpoint (like ollama / omniroute) or Tavily endpoint is hit
    import requests
    original_post = requests.post
    
    post_calls = []
    def mock_post(url, *args, **kwargs):
        post_calls.append(url)
        # Block actual outbound requests if any to LLM/Tavily, but let Qdrant pass
        if "localhost" in url or "127.0.0.1" in url or "qdrant" in url:
            return original_post(url, *args, **kwargs)
        raise AssertionError(f"Outbound request intercepted: POST {url}")

    service = SkillGapService()
    
    t0 = time.perf_counter()
    with patch("requests.post", side_effect=mock_post):
        report = service.get_skill_gap_report(
            student=student_id,
            career=career_profile
        )
    t_duration = (time.perf_counter() - t0) * 1000.0
    
    print("=================== PERFORMANCE & DEPENDENCY AUDIT ===================")
    print(f"Report generated successfully in {t_duration:.2f} ms")
    print(f"Readiness Score: {report.readiness_score}%")
    print(f"Ready for Job: {report.ready_for_job}")
    print(f"Matched Skills: {report.matched_skills}")
    print(f"Missing Foundation: {report.missing_foundation}")
    print(f"Missing Core Domain: {report.missing_core_domain}")
    print(f"Missing Industry: {report.missing_industry}")
    print(f"Missing Emerging: {report.missing_emerging}")
    print(f"Priority Order: {report.priority_order}")
    print(f"HTTP Post calls made: {post_calls}")
    
    # Assertions
    assert "api/generate" not in "".join(post_calls), "LLM should not be called!"
    assert "tavily" not in "".join(post_calls), "Tavily should not be called!"
    print("ALL DEPENDENCY TESTS PASSED! 0 LLM/Tavily calls detected during deterministic gap calculation.")

    # Cleanup
    frappe.db.delete("Student", {"name": student_id})
    frappe.db.delete("Student Skill", {"student": student_id})
    frappe.db.commit()

if __name__ == "__main__":
    test_performance()
