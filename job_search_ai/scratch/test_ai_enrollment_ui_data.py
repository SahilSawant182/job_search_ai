import frappe
from unittest.mock import patch
from nexedu.path_finder.api.path_enrollment import enroll_student
from nexedu.path_finder.app_api import get_active_plan
from job_search_ai.agents.roadmap_agent.schemas import RoadmapResult, RoadmapProfile, RoadmapMilestone

def run_test():
    # Delete old enrollment
    frappe.db.delete("Student Path Enrollment", {"student": "ac1@gmail.com"})
    frappe.db.commit()

    # Create mock roadmap
    m1 = RoadmapMilestone(sequence=1, title="Master Python Programming", type="Learn", skill="Programming languages", skill_tier="Foundation", duration_days=10, objective="Learn basic python syntax", project="Calculator app")
    m2 = RoadmapMilestone(sequence=2, title="Master Creativity", type="Learn", skill="Creativity", skill_tier="Foundation", duration_days=10, objective="Do creative thinking exercises", project="Journal writing")
    m3 = RoadmapMilestone(sequence=3, title="Master Machine Learning", type="Learn", skill="Lead generation", skill_tier="Core Domain", duration_days=15, objective="Learn ML basics", project="Classification project")
    mock_res = RoadmapResult(roadmap=RoadmapProfile(career="AI Engineer", readiness_score=40.0, milestones=[m1, m2, m3]), validation_status="Valid")

    # Enroll student
    with patch("job_search_ai.agents.roadmap_agent.agent.RoadmapAgent.run", return_value=mock_res):
        res = enroll_student(student="ac1@gmail.com", career_path="AI Engineer", force_enroll=1, path_generation_mode="AI")
        print("Enrollment result:", res)

    # Get active plan details
    plan = get_active_plan("ac1@gmail.com")
    print("Milestones in active plan:")
    for m in plan["milestones"]:
        print(f"Title: {m['milestone_title']} | Skill: {m['skill']} | Level: {m['required_skill_level']} | Category: {m['category']} | IsPrereq: {m['is_prereq']} | Status: {m['status']}")

if __name__ == "__main__":
    run_test()
