import frappe
import json
import traceback
from job_search_ai.agents.roadmap_agent.agent import RoadmapAgent
from job_search_ai.agents.roadmap_agent.schemas import RoadmapResult
from nexedu.path_finder.api.path_enrollment import enroll_student
from job_search_ai.tasks import generate_personalized_roadmap

def run():
    print("=================== STARTING ROADMAP END-TO-END DIAGNOSIS ===================")
    
    # 1. Setup mock student and career path
    student_email = "diag_student@example.com"
    career_path = "AI Engineer"

    # Ensure clean state
    frappe.db.delete("Roadmap Template", {"career_path": career_path})
    frappe.db.delete("Student Path Enrollment", {"student": student_email})
    frappe.db.delete("Student Skill", {"student": student_email})
    frappe.db.delete("Student", {"email_id": student_email})
    
    # Ensure student profile has academic details
    college = frappe.db.get_value("College", {}, "name")
    if not college:
        col = frappe.get_doc({"doctype": "College", "college_name": "Test College"})
        col.insert(ignore_permissions=True)
        college = col.name
        
    student = frappe.get_doc({
        "doctype": "Student",
        "first_name": "Diagnostic",
        "last_name": "Student",
        "email_id": student_email,
        "college": college,
        "current_year": "Third Year",
        "cgpa": 8.7,
        "course": "MTech",
        "department": "Information Technology",
        "career_interest": [
            {"interest": "Natural Language Processing"},
            {"interest": "Computer Vision"}
        ]
    })
    student.insert(ignore_permissions=True)

    # Ensure Career Path and Skills exist
    for s in ["Machine Learning", "Deep Learning", "PyTorch", "AWS"]:
        if not frappe.db.exists("Skill", s):
            frappe.get_doc({"doctype": "Skill", "skill_name": s}).insert(ignore_permissions=True)

    if not frappe.db.exists("Career Path", career_path):
        cp = frappe.get_doc({
            "doctype": "Career Path",
            "path_name": career_path,
            "target_role": career_path,
            "difficulty_level": "Moderate",
            "estimated_duration_months": 6
        })
        cp.append("prerequisite_skills", {"prerequisite_skills": "Machine Learning", "level": "Intermediate"})
        cp.append("prerequisite_skills", {"prerequisite_skills": "Deep Learning", "level": "Intermediate"})
        cp.append("path_milestone", {"milestone_title": "Master PyTorch", "milestone_type": "Learn", "skill": "PyTorch", "required_skill_level": "Intermediate", "duration_days": 14})
        cp.append("path_milestone", {"milestone_title": "Master AWS", "milestone_type": "Learn", "skill": "AWS", "required_skill_level": "Intermediate", "duration_days": 10})
        cp.insert(ignore_permissions=True)

    # Let's say our student already has "Machine Learning" as verified
    frappe.get_doc({
        "doctype": "Student Skill",
        "student": student_email,
        "skill": "Machine Learning",
        "current_level": "Intermediate",
        "status": "Verified",
        "ai_verified": 1
    }).insert(ignore_permissions=True)

    frappe.db.commit()

    print("\n[Step 1] Initial Student Context:")
    print(f"  - CGPA: {student.cgpa}")
    print(f"  - Course: {student.course}")
    print(f"  - Interests: {[i.interest for i in student.career_interest]}")
    print(f"  - Already Knows (Verified): Machine Learning")

    # 2. Trigger Enrollment (Cache MISS flow)
    print("\n[Step 2] Triggering Path Enrollment (Should result in Cache MISS)...")
    res = enroll_student(student=student_email, career_path=career_path, path_generation_mode="AI")
    frappe.db.commit()
    print(f"  - Enrollment Response: {res}")
    
    enrollment_id = res.get("enrollment")
    enroll_doc = frappe.get_doc("Student Path Enrollment", enrollment_id)
    print(f"  - Enrollment Doc Status: {enroll_doc.status}")

    # 3. Execute Background Generator Synchronously
    print("\n[Step 3] Running generate_personalized_roadmap (Cache MISS / AI Generation)...")
    
    # We will hook into the run function of RoadmapAgent and LLMService to spy on prompt/response
    from job_search_ai.agents.roadmap_agent.llm_service import LLMService
    original_run = RoadmapAgent.run
    original_call_agent = LLMService.call_agent
    captured_data = {}
    
    def spy_run(self, student, career, skill_gap_report=None):
        print("\n  >>> RoadmapAgent.run() invoked!")
        print(f"  >>> Target Student parameter: {student}")
        print(f"  >>> Target Career: {career}")
        result = original_run(self, student, career, skill_gap_report)
        captured_data["result"] = result
        return result

    def spy_call_agent(self, prompt):
        print("\n=== LLM PROMPT ===")
        print(prompt)
        print("==================\n")
        response = original_call_agent(self, prompt)
        print("\n=== LLM RESPONSE ===")
        print(response)
        print("====================\n")
        return response

    try:
        RoadmapAgent.run = spy_run
        LLMService.call_agent = spy_call_agent
        frappe.db.commit()
        generate_personalized_roadmap(enrollment_id)
    except Exception as ex:
        print("\n  [ERROR] Background generation task failed:")
        traceback.print_exc()
    finally:
        RoadmapAgent.run = original_run
        LLMService.call_agent = original_call_agent

    # 4. Verify template generated
    print("\n[Step 4] Checking Roadmap Template Cache:")
    template_exists = frappe.db.exists("Roadmap Template", career_path)
    print(f"  - Template for '{career_path}' exists in database: {template_exists}")
    
    if template_exists:
        t_doc = frappe.get_doc("Roadmap Template", career_path)
        print("  - Milestones stored in Template:")
        milestones = json.loads(t_doc.milestones_json)
        # Handle dict or list format
        if isinstance(milestones, dict):
            milestones = milestones.get("milestones", [])
        for m in milestones:
            print(f"    * Sequence {m.get('sequence')}: {m.get('title')} (Skill: {m.get('skill')})")
            print(f"      - Completion Criteria: {m.get('completion_criteria')}")
            print(f"      - Learning Outcomes: {m.get('learning_outcomes')}")
            print(f"      - Supporting Skills: {m.get('supporting_skills')}")

    # 5. Verify enrollment personalized
    print("\n[Step 5] Checking personalized student enrollment milestones:")
    enroll_doc.reload()
    print(f"  - Enrollment Status: {enroll_doc.status}")
    print(f"  - AI Recommended flag: {enroll_doc.ai_recommended}")
    
    print("  - Student Milestones Progress Table:")
    for mp in enroll_doc.milestone_progress:
        print(f"    * {mp.milestone_title} (Skill: {mp.skill})")
        print(f"      - Status: {mp.status}")
        print(f"      - Auto-skipped? {mp.is_auto_skipped}")

    # 6. Trigger Enrollment AGAIN (Cache HIT flow)
    print("\n[Step 6] Re-enrolling (Should result in Cache HIT)...")
    # First, let's pause the existing one to simulate enrolling again
    enroll_doc.status = "Paused"
    enroll_doc.save(ignore_permissions=True)
    frappe.db.commit()

    res_hit = enroll_student(student=student_email, career_path=career_path, path_generation_mode="AI")
    print(f"  - Re-enrollment Response: {res_hit}")
    
    enrollment_id_hit = res_hit.get("enrollment")
    enroll_doc_hit = frappe.get_doc("Student Path Enrollment", enrollment_id_hit)
    print(f"  - Re-enrollment Doc Status: {enroll_doc_hit.status} (Expected: Active)")
    print(f"  - Re-enrollment Milestones Progress Table:")
    for mp in enroll_doc_hit.milestone_progress:
        print(f"    * {mp.milestone_title} (Skill: {mp.skill})")
        print(f"      - Status: {mp.status}")
        print(f"      - Auto-skipped? {mp.is_auto_skipped}")

    print("\n[Step 7] Checking Frappe Error Logs:")
    logs = frappe.db.sql(
        "SELECT method, error FROM `tabError Log` ORDER BY creation DESC LIMIT 10",
        as_dict=True
    )
    for l in logs:
        print(f"  - Error Log ({l.method}):\n{l.error[:500] if l.error else 'N/A'}")

    print("\n=================== DIAGNOSIS COMPLETE ===================")
