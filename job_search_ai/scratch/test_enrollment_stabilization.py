import frappe
from nexedu.path_finder.api.path_enrollment import enroll_student
from nexedu.path_finder.app_api import get_student_career_path

def run():
    print("=== TESTING ENROLLMENT STABILIZATION ===")
    
    student = "ac1@gmail.com"
    career_path = "Frappe Developer"
    
    # 1. Clean up existing enrollments for this path
    existing = frappe.get_all(
        "Student Path Enrollment",
        filters={"student": student, "career_path": career_path},
        pluck="name"
    )
    for name in existing:
        print(f"Deleting existing enrollment: {name}")
        frappe.delete_doc("Student Path Enrollment", name, ignore_permissions=True)
    frappe.db.commit()
    
    # 2. Call enroll_student
    print(f"\nEnrolling student {student} in {career_path} with AI...")
    res = enroll_student(student=student, career_path=career_path, path_generation_mode="AI")
    print("Enroll result:", res)
    
    # 3. Check enrollment state
    enrollment_id = res.get("enrollment")
    doc = frappe.get_doc("Student Path Enrollment", enrollment_id)
    print(f"Enrollment Status: {doc.status}")
    print(f"Milestones count: {len(doc.milestone_progress)}")
    
    # 4. Check get_student_career_path return value
    path_state = get_student_career_path(student)
    print("Active path state from API:", path_state.get("type"))
    
    # 5. Let's simulate a failed enrollment by pausing it and clearing milestones
    print("\nSimulating failed generation...")
    doc.status = "Paused"
    doc.milestone_progress = []
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    
    path_state = get_student_career_path(student)
    print("State after failure simulation:", path_state.get("type"))
    print("Expected state: failed")
    
    # 6. Retry enrolling after failure
    print("\nRetrying enrollment...")
    res_retry = enroll_student(student=student, career_path=career_path, path_generation_mode="AI")
    print("Retry result:", res_retry)
    
    doc_retry = frappe.get_doc("Student Path Enrollment", res_retry.get("enrollment"))
    print(f"Retry Enrollment Status: {doc_retry.status}")
    print(f"Retry Milestones count: {len(doc_retry.milestone_progress)}")

    # 7. Verify paginated career paths API
    print("\n=== TESTING PAGINATED CAREER PATHS API ===")
    from nexedu.path_finder.app_api import get_all_career_paths
    
    # Test first page
    res_page1 = get_all_career_paths(page=1, page_length=5)
    print("Page 1 keys:", list(res_page1.keys()))
    print("Page 1 paths count:", len(res_page1.get("paths", [])))
    print("Total Count:", res_page1.get("total_count"))
    print("Total Pages:", res_page1.get("total_pages"))
    
    # Test search query
    res_search = get_all_career_paths(search_query="AI", page=1, page_length=5)
    print("\nSearch for 'AI' count:", len(res_search.get("paths", [])))
    for p in res_search.get("paths", []):
        print(f" - {p.get('path_name')} (Skills: {p.get('skills')})")

if __name__ == "__main__":
    run()
