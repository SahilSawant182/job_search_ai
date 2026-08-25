import frappe
import time
from job_search_ai.tasks import generate_personalized_roadmap

def test_python_developer_flow():
    student_email = "stu2@gmail.com"
    career_path = "Python Developer"

    print("Cleaning up old enrollment and skill records...")
    frappe.db.delete("Student Path Enrollment", {"student": student_email, "career_path": career_path})
    frappe.db.delete("Student Skill", {"student": student_email})
    
    # Delete and recreate Career Path to ensure clean milestones
    if frappe.db.exists("Career Path", career_path):
        print(f"Deleting bloated Career Path: {career_path}")
        frappe.delete_doc("Career Path", career_path, force=True)
        
    frappe.db.commit()

    # Ensure Student exists
    if not frappe.db.exists("Student", student_email):
        college = frappe.db.get_value("College", {}, "name") or "Default College"
        stu = frappe.get_doc({
            "doctype": "Student",
            "first_name": "Test",
            "last_name": "Student",
            "email_id": student_email,
            "college": college
        })
        stu.insert(ignore_permissions=True)
        frappe.db.commit()

    print(f"Creating clean Career Path: {career_path}")
    cp = frappe.get_doc({
        "doctype": "Career Path",
        "path_name": career_path,
        "path_type": "Job",
        "difficulty_level": "Moderate",
        "target_role": career_path,
        "estimated_duration_months": 3,
        "published": 1,
        "prerequisite_skills": [
            {"doctype": "Prerequisite Skills", "prerequisite_skills": "Git", "level": "Beginner"},
            {"doctype": "Prerequisite Skills", "prerequisite_skills": "SQL", "level": "Beginner"}
        ],
        "path_milestone": [
            {"doctype": "Path Milestone", "milestone_title": "Master Python Programming", "category": "Core Domain", "skill": "Python", "milestone_type": "Learn", "required_skill_level": "Intermediate", "is_mandatory": 1, "duration_days": 10},
            {"doctype": "Path Milestone", "milestone_title": "Master Django Framework", "category": "Core Domain", "skill": "Django", "milestone_type": "Learn", "required_skill_level": "Intermediate", "is_mandatory": 1, "duration_days": 12},
            {"doctype": "Path Milestone", "milestone_title": "Build RESTful APIs with Flask", "category": "Core Domain", "skill": "Flask", "milestone_type": "Learn", "required_skill_level": "Intermediate", "is_mandatory": 1, "duration_days": 10},
            {"doctype": "Path Milestone", "milestone_title": "Deploy to Amazon Web Services", "category": "Industry", "skill": "Amazon Web Services", "milestone_type": "Learn", "required_skill_level": "Intermediate", "is_mandatory": 0, "duration_days": 14}
        ]
    })
    cp.insert(ignore_permissions=True)
    frappe.db.commit()

    print("Creating new Student Path Enrollment...")
    enrollment = frappe.get_doc({
        "doctype": "Student Path Enrollment",
        "student": student_email,
        "career_path": career_path,
        "status": "Pending",
        "enrolled_at": frappe.utils.now_datetime()
    })
    enrollment.insert(ignore_permissions=True)
    frappe.db.commit()

    print(f"Enrolled successfully. Enrollment ID: {enrollment.name}")
    print("Clearing local document cache to avoid TimestampMismatchError...")
    frappe.clear_document_cache("Student Path Enrollment", enrollment.name)
    if hasattr(frappe.local, "document_cache"):
        frappe.local.document_cache.clear()

    print("Running generate_personalized_roadmap synchronously...")
    t_start = time.perf_counter()
    generate_personalized_roadmap(enrollment.name)
    t_duration = time.perf_counter() - t_start

    print(f"\nCompleted in {t_duration:.2f} seconds!")

    # Load enrollment to check results
    enrollment.reload()
    print(f"Status: {enrollment.status}")
    print(f"AI Recommended: {enrollment.ai_recommended}")
    print(f"Milestones generated: {len(enrollment.milestone_progress)}")
    for idx, m in enumerate(enrollment.milestone_progress):
        print(f"  {idx+1}. [{m.category}] {m.milestone_title} (Skill: {m.skill}, Status: {m.status}, Prereq: {m.is_prereq})")

if __name__ == '__main__':
    frappe.connect("devstridenex.quantcloud.in")
    test_python_developer_flow()
