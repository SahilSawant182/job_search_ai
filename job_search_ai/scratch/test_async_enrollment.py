# -*- coding: utf-8 -*-
import frappe
from nexedu.path_finder.api.path_enrollment import enroll_student
from job_search_ai.tasks import generate_personalized_roadmap
import time

def run_test():
    print("================================================================================")
    print("   TESTING ASYNC ENROLLMENT PIPELINE")
    print("================================================================================")
    
    frappe.db.connect()
    
    # 1. Setup test student
    student_email = "async_test_student@stridenex.com"
    if not frappe.db.exists("Student", {"email_id": student_email}):
        student_doc = frappe.get_doc({
            "doctype": "Student",
            "first_name": "Async",
            "last_name": "Tester",
            "email_id": student_email,
            "gender": "Male",
            "date_of_birth": "2000-01-01",
            "college": "Tanvi International",
            "interests": "AI, Data Science"
        })
        student_doc.insert(ignore_permissions=True)
        print(f"Created test student: {student_email}")
    else:
        student_doc = frappe.get_doc("Student", {"email_id": student_email})
        student_doc.interests = "AI, Data Science"
        student_doc.save(ignore_permissions=True)
        print(f"Using existing test student: {student_email}")

    # 2. Test Career Path
    career_path = "Research Data Scientist"
    if not frappe.db.exists("Career Path", career_path):
        print(f"Career Path '{career_path}' does not exist! Please check.")
        return

    # Delete any existing enrollments for this test student
    frappe.db.delete("Student Path Enrollment", {"student": student_email})
    frappe.db.commit()

    # 3. Trigger Async Enrollment
    print("\n[Step 1] Triggering enroll_student with path_generation_mode='AI'...")
    res = enroll_student(
        student=student_email,
        career_path=career_path,
        path_generation_mode="AI"
    )
    print(f"Response: {res}")
    
    # Assert return status
    assert res.get("status") == "generating"
    enrollment_name = res.get("enrollment")
    assert enrollment_name is not None
    
    # Check that status is Generating
    doc = frappe.get_doc("Student Path Enrollment", enrollment_name)
    print(f"Created enrollment status: '{doc.status}'")
    assert doc.status == "Generating"
    assert doc.ai_recommended == 1
    assert len(doc.milestone_progress) == 0

    # 4. Poll database for background completion
    print("\n[Step 2] Polling database for async background generation...")
    max_wait = 300  # wait up to 5 minutes
    start_time = time.time()
    completed = False
    
    while time.time() - start_time < max_wait:
        doc.reload()
        if doc.status != "Generating":
            completed = True
            break
        print(f"  ... Still generating (elapsed: {int(time.time() - start_time)}s)")
        time.sleep(5)
        
    if not completed:
        raise TimeoutError("Background task timed out or failed to start.")
        
    print(f"Completed enrollment status: '{doc.status}'")
    print(f"Completed enrollment ai_recommended flag: '{doc.ai_recommended}'")
    print(f"Completed enrollment milestone progress rows count: {len(doc.milestone_progress)}")
    
    # Assert activation and milestones
    assert doc.status in ("Active", "Paused")
    assert len(doc.milestone_progress) > 0
    
    print(f"AI Recommended matches expectations? (ai_recommended={doc.ai_recommended})")

    # 5. Clean up
    frappe.db.delete("Student Path Enrollment", {"student": student_email})
    frappe.db.delete("Student", {"email_id": student_email})
    frappe.db.commit()
    print("\nTest completed successfully and cleanup done.")

if __name__ == "__main__":
    run_test()
