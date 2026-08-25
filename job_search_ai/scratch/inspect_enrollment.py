import frappe

def run():
    print("=== INSPECTING RECENT ENROLLMENTS ===")
    enrollments = frappe.get_all(
        "Student Path Enrollment",
        fields=["name", "student", "career_path", "status", "creation"],
        order_by="creation desc",
        limit=5
    )
    for e in enrollments:
        print(f"Enrollment: {e.name} | Student: {e.student} | Path: {e.career_path} | Status: {e.status} | Created: {e.creation}")
        doc = frappe.get_doc("Student Path Enrollment", e.name)
        print(f"  Milestones count: {len(doc.milestone_progress)}")
        print(f"  Milestone points count: {len(doc.get('milestone_points') or [])}")
