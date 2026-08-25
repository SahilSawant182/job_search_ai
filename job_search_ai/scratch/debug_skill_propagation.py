import frappe
from nexedu.path_finder.api.path_enrollment import enroll_student, complete_milestone_point
from frappe.utils.password import update_password

def run_debug():
    print("=========================================")
    print("STARTING DEBUG OF SKILL PROPAGATION (NEW & UPGRADE scenarios)")
    print("=========================================")
    
    email = "test_prop@example.com"
    career_path = "AI Engineer"
    
    # 1. Clean up existing test data
    frappe.db.delete("Student Path Enrollment", {"student": email})
    frappe.db.delete("Student Skill", {"student": email})
    frappe.db.delete("Student", {"email_id": email})
    frappe.db.delete("User", {"name": email})
    frappe.db.commit()
    print("Cleaned up old records.")
    
    # 2. Get College
    college = frappe.db.get_value("College", {}, "name")
    if not college:
        col = frappe.get_doc({"doctype": "College", "college_name": "Acceptance Test College"})
        col.insert(ignore_permissions=True)
        college = col.name
        
    # 3. Create User and Student
    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": "Test",
        "last_name": "Prop",
        "enabled": 1,
        "send_welcome_email": 0,
        "is_onboarded": 2
    })
    user.insert(ignore_permissions=True)
    update_password(email, "password123")
    
    student = frappe.get_doc({
        "doctype": "Student",
        "first_name": "Test",
        "last_name": "Prop",
        "email_id": email,
        "college": college
    })
    student.insert(ignore_permissions=True)
    frappe.db.commit()
    print("Created Student record successfully.")
    
    # ----------------------------------------------------
    # SCENARIO 1: NEW STUDENT SKILL CREATION
    # ----------------------------------------------------
    print("\n--- SCENARIO 1: New Student Skill ---")
    
    # Enroll student
    res = enroll_student(student=email, career_path=career_path, path_generation_mode="AI")
    enrollment_id = res.get("enrollment")
    print(f"Enrolled student. Enrollment ID: {enrollment_id}")
    
    # Ensure personalized roadmap is generated/seeded
    enr_doc = frappe.get_doc("Student Path Enrollment", enrollment_id)
    if enr_doc.status == "Generating":
        print("Roadmap generating... Running personalization synchronously.")
        from job_search_ai.tasks import generate_personalized_roadmap
        generate_personalized_roadmap(enrollment_id)
        enr_doc.reload()
        
    print(f"Enrollment status after generation: {enr_doc.status}")
    print(f"Total milestones: {len(enr_doc.milestone_progress)}")
    
    # Let's inspect the first milestone (typically Deep Learning)
    first_m = enr_doc.milestone_progress[0]
    print(f"First Milestone: {first_m.milestone_title} | Skill: {first_m.skill} | Status: {first_m.status}")
    
    # Check if there are checklist points
    points = [p for p in enr_doc.milestone_points if p.milestone_title == first_m.milestone_title]
    print(f"Points for first milestone: {len(points)}")
    
    # Complete checklist points
    for p in points:
        print(f"Completing point: {p.point_title}")
        res = complete_milestone_point(
            enrollment=enrollment_id,
            milestone_title=first_m.milestone_title,
            point_title=p.point_title,
            completed=True
        )
        print(f"Result: {res}")
        
    # Reload enrollment
    enr_doc.reload()
    print(f"First Milestone status after completing points: {enr_doc.milestone_progress[0].status}")
    
    # Check Student Skill for Scenario 1
    skills_s1 = frappe.db.get_all("Student Skill", filters={"student": email, "skill": first_m.skill}, fields=["name", "current_level", "status", "ai_verified", "self_declared"])
    print(f"Student Skills for {first_m.skill} in DB (Scenario 1): {skills_s1}")
    assert len(skills_s1) == 1, "Scenario 1: Student Skill should be created."
    assert skills_s1[0]["ai_verified"] == 1, "Scenario 1: Student Skill should be AI verified."
    assert skills_s1[0]["status"] == "Verified", "Scenario 1: Student Skill status should be Verified."
    print("Scenario 1 validation PASSED!")

    # ----------------------------------------------------
    # SCENARIO 2: EXISTING STUDENT SKILL UPGRADE
    # ----------------------------------------------------
    print("\n--- SCENARIO 2: Existing Student Skill Upgrade ---")
    
    # Clean up the enrollment
    frappe.db.delete("Student Path Enrollment", {"student": email})
    frappe.db.delete("Student Skill", {"student": email})
    frappe.db.commit()
    print("Cleaned up old records for Scenario 2.")
    
    # Pre-create Student Skill for "Deep Learning" as Beginner, not AI-verified
    pre_skill = frappe.get_doc({
        "doctype": "Student Skill",
        "student": email,
        "skill": "Deep Learning",
        "current_level": "Beginner",
        "self_declared": 1,
        "ai_verified": 0,
        "is_public": 1
    })
    pre_skill.insert(ignore_permissions=True)
    frappe.db.commit()
    print("Pre-created Deep Learning skill as Beginner / Unverified.")
    
    # Enroll student again
    res = enroll_student(student=email, career_path=career_path, path_generation_mode="AI")
    enrollment_id = res.get("enrollment")
    print(f"Enrolled student. Enrollment ID: {enrollment_id}")
    
    # Ensure personalized roadmap is generated/seeded
    enr_doc = frappe.get_doc("Student Path Enrollment", enrollment_id)
    if enr_doc.status == "Generating":
        print("Roadmap generating... Running personalization synchronously.")
        from job_search_ai.tasks import generate_personalized_roadmap
        generate_personalized_roadmap(enrollment_id)
        enr_doc.reload()
        
    # Get first milestone which requires Intermediate/Advanced
    first_m = enr_doc.milestone_progress[0]
    print(f"First Milestone: {first_m.milestone_title} | Skill: {first_m.skill} | Required level: {first_m.required_skill_level}")
    
    # Complete all checklist points
    points = [p for p in enr_doc.milestone_points if p.milestone_title == first_m.milestone_title]
    for p in points:
        complete_milestone_point(
            enrollment=enrollment_id,
            milestone_title=first_m.milestone_title,
            point_title=p.point_title,
            completed=True
        )
        
    # Check Student Skill for Scenario 2
    skills_s2 = frappe.db.get_all("Student Skill", filters={"student": email, "skill": first_m.skill}, fields=["name", "current_level", "status", "ai_verified", "self_declared"])
    print(f"Student Skills for {first_m.skill} in DB (Scenario 2): {skills_s2}")
    assert len(skills_s2) == 1, "Scenario 2: Student Skill should still exist."
    assert skills_s2[0]["current_level"] == first_m.required_skill_level or "Intermediate", "Scenario 2: Level should be upgraded."
    assert skills_s2[0]["ai_verified"] == 1, "Scenario 2: Student Skill should become AI verified."
    assert skills_s2[0]["status"] == "Verified", "Scenario 2: Student Skill status should become Verified."
    print("Scenario 2 validation PASSED!")

if __name__ == "__main__":
    run_debug()
