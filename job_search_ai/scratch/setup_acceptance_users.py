import frappe
from frappe.utils.password import update_password

def setup_users():
    test_students = {
        "beginner_student@example.com": {
            "first_name": "Beginner",
            "skills": ["Python"]
        },
        "intermediate_student@example.com": {
            "first_name": "Intermediate",
            "skills": ["Python", "Git", "SQL"]
        },
        "advanced_student@example.com": {
            "first_name": "Advanced",
            "skills": ["Python", "Git", "SQL", "PyTorch"]
        },
        "nogap_student@example.com": {
            "first_name": "NoGap",
            "skills": ["Python", "Git", "SQL", "PyTorch", "Amazon Web Services", "Deep Learning", "Machine Learning"]
        }
    }
    
    # 1. Clean up existing records for these test emails and AI Engineer links
    emails = list(test_students.keys())
    for email in emails:
        # Delete logs referencing enrollments
        enrollments = frappe.get_all("Student Path Enrollment", filters={"student": email}, pluck="name")
        if enrollments:
            frappe.db.delete("Path Progress Log", {"enrollment": ["in", enrollments]})
        # Delete Enrollments
        frappe.db.delete("Student Path Enrollment", {"student": email})
        frappe.db.delete("Student Skill", {"student": email})
        frappe.db.delete("Student", {"email_id": email})
        frappe.db.delete("Has Role", {"parent": email})
        frappe.db.delete("DocShare", {"share_doctype": "User", "share_name": email})
        frappe.db.delete("User", {"name": email})
            
    # Purge all AI Engineer enrollments, logs, and the career path doc itself so it can be regenerated cleanly
    frappe.db.delete("Path Progress Log", {"career_path": "AI Engineer"})
    frappe.db.delete("Student Path Enrollment", {"career_path": "AI Engineer"})
    frappe.delete_doc("Career Path", "AI Engineer", ignore_permissions=True, force=True)
    frappe.db.commit()
    print("Cleaned up existing acceptance test records and purged AI Engineer.")

    # Pre-generate/seed the AI Engineer Career Path synchronously from the CLI
    # to avoid web request timeouts (502 Bad Gateway) during API execution.
    print("Seeding AI Engineer Career Path...")
    from nexedu.path_finder.api.path_enrollment import check_and_create_career_path
    check_and_create_career_path("AI Engineer")
    frappe.db.commit()
    print("AI Engineer Career Path successfully seeded.")
    
    # 2. Clear any AI Engineer Roadmap Template to ensure Scenario 1 is a Cache MISS
    frappe.delete_doc("Roadmap Template", "AI Engineer", ignore_missing=True, force=True)
    frappe.db.commit()
    print("Cleared AI Engineer Roadmap Template.")
    
    # 3. Resolve College
    college = frappe.db.get_value("College", {}, "name")
    if not college:
        col = frappe.get_doc({"doctype": "College", "college_name": "Acceptance Test College"})
        col.insert(ignore_permissions=True)
        college = col.name
        
    # 4. Create Users, Students, and Student Skills
    for email, info in test_students.items():
        # Create User
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": info["first_name"],
            "last_name": "Student",
            "enabled": 1,
            "send_welcome_email": 0,
            "is_onboarded": 2
        })
        user.insert(ignore_permissions=True)
        
        # Set Roles
        user.add_roles("Student Base", "Student", "Raven User")
        
        # Set Password
        update_password(email, "password123")
        
        # Create Student
        student = frappe.get_doc({
            "doctype": "Student",
            "first_name": info["first_name"],
            "last_name": "Student",
            "email_id": email,
            "college": college
        })
        student.insert(ignore_permissions=True)
        
        # Insert Skills
        for skill_name in info["skills"]:
            if not frappe.db.exists("Skill", skill_name):
                frappe.get_doc({"doctype": "Skill", "skill_name": skill_name}).insert(ignore_permissions=True)
            
            student_skill = frappe.get_doc({
                "doctype": "Student Skill",
                "student": student.name,
                "skill": skill_name,
                "current_level": "Intermediate",
                "self_declared": 0,
                "is_public": 1,
                "ai_verified": 1
            })
            student_skill.insert(ignore_permissions=True)
            frappe.db.set_value("Student Skill", student_skill.name, "status", "Verified")
            frappe.db.set_value("Student Skill", student_skill.name, "ai_verified", 1)
            
        print(f"Created student User & record for {email} with password 'password123' and skills: {info['skills']}")
        
    frappe.db.commit()
    print("Acceptance test environment successfully prepared.")

if __name__ == "__main__":
    setup_users()
