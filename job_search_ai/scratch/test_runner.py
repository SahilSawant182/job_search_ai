import frappe
from unittest.mock import patch, MagicMock
import json

def run_diagnostic():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    print("=== Starting Diagnostic Run ===")

    # Setup environment
    student_a = "student_a@example.com"
    student_b = "student_b@example.com"
    career_path = "AI Engineer"

    # Clean existing
    frappe.db.delete("Student Path Enrollment", {"student": ["in", [student_a, student_b]]})
    frappe.db.delete("Roadmap Template", {"career_path": career_path})
    frappe.delete_doc("Career Path", "AI Engineer", ignore_permissions=True, force=True)
    frappe.db.commit()

    # Ensure Skills exist in database
    for s in ["Machine Learning", "Deep Learning", "PyTorch", "AWS"]:
        if not frappe.db.exists("Skill", s):
            frappe.get_doc({"doctype": "Skill", "skill_name": s}).insert(ignore_permissions=True)

    frappe.db.delete("Student Skill", {"student": ["in", [student_a, student_b]]})
    
    doc_a = frappe.get_doc({
        "doctype": "Student Skill",
        "student": student_a,
        "skill": "Machine Learning",
        "current_level": "Intermediate",
        "status": "Verified",
        "ai_verified": 1
    }).insert(ignore_permissions=True)
    frappe.db.set_value("Student Skill", doc_a.name, "status", "Verified")

    doc_b = frappe.get_doc({
        "doctype": "Student Skill",
        "student": student_b,
        "skill": "Deep Learning",
        "current_level": "Intermediate",
        "status": "Verified",
        "ai_verified": 1
    }).insert(ignore_permissions=True)
    frappe.db.set_value("Student Skill", doc_b.name, "status", "Verified")

    # Ensure Career Path exists and has prerequisites
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

    frappe.db.commit()

    from job_search_ai.agents.roadmap_agent.schemas import RoadmapProfile, RoadmapMilestone, RoadmapResult
    mock_generic_roadmap = RoadmapProfile(
        career=career_path,
        readiness_score=0.0,
        milestones=[
            RoadmapMilestone(
                sequence=1, title="Master ML", type="Learn", skill="Machine Learning",
                skill_tier="Foundation", duration_days=10, objective="ML Obj", project="ML Proj",
                points=["point1"], completion_criteria=["crit1"], learning_outcomes=["out1"], supporting_skills=[]
            ),
            RoadmapMilestone(
                sequence=2, title="Master DL", type="Learn", skill="Deep Learning",
                skill_tier="Core Domain", duration_days=14, objective="DL Obj", project="DL Proj",
                points=["point2"], completion_criteria=["crit2"], learning_outcomes=["out2"], supporting_skills=[]
            ),
            RoadmapMilestone(
                sequence=3, title="Master PyTorch", type="Build", skill="PyTorch",
                skill_tier="Core Domain", duration_days=14, objective="PyTorch Obj", project="PyTorch Proj",
                points=["point3"], completion_criteria=["crit3"], learning_outcomes=["out3"], supporting_skills=[]
            ),
            RoadmapMilestone(
                sequence=4, title="Master AWS", type="Apply", skill="AWS",
                skill_tier="Industry", duration_days=10, objective="AWS Obj", project="AWS Proj",
                points=["point4"], completion_criteria=["crit4"], learning_outcomes=["out4"], supporting_skills=[]
            )
        ]
    )

    with patch("job_search_ai.agents.roadmap_agent.agent.RoadmapAgent.run") as mock_run:
        mock_run.return_value = RoadmapResult(
            roadmap=mock_generic_roadmap,
            validation_status="Valid",
            metrics={"generation_mode": "AI"}
        )

        from nexedu.path_finder.api.path_enrollment import enroll_student
        res_a = enroll_student(student=student_a, career_path=career_path, path_generation_mode="AI")
        print(f"Enrollment response: {res_a}")

        enroll_a = frappe.get_doc("Student Path Enrollment", res_a["enrollment"])
        print(f"Initial Enrollment Status: {enroll_a.status}")

        print("Manually running generate_personalized_roadmap...")
        from job_search_ai.tasks import generate_personalized_roadmap
        try:
            generate_personalized_roadmap(enroll_a.name)
        except Exception as ex:
            import traceback
            traceback.print_exc()

        enroll_a.reload()
        print(f"Post-run Enrollment Status: {enroll_a.status}")

if __name__ == "__main__":
    run_diagnostic()
