# -*- coding: utf-8 -*-
import sys
import frappe
sys.path.append("/home/dev/frappe-bench/apps/job_search_ai")

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    from job_search_ai.agents.career_trend.schemas import StudentProfile
    from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine

    student = StudentProfile(
        degree="B.Tech",
        branch="Computer Science",
        year=2,
        country="India",
        interests=["Frontend Development", "Web Development", "UI Development"],
        skills=["HTML", "CSS", "JavaScript"]
    )
    retrieved = frappe.get_all("Career Knowledge")
    loaded = []
    for r in retrieved:
        try:
            loaded.append(frappe.get_doc("Career Knowledge", r.name))
        except:
            pass
    engine = RecommendationEngine()
    scored = engine.rank(student, loaded)
    print("Number of scored candidates:", len(scored))
    for sc in scored[:10]:
        cand_skills = [s.skill_name for s in sc.candidate.skills]
        print(f"Career: {sc.candidate.career_name} | Score: {sc.final_score:.4f} | Skills match: {sc.scores['skill_match']:.4f} | Interest match: {sc.scores['interest_match']:.4f}")
        print(f"  Candidate skills: {cand_skills}")


if __name__ == "__main__":
    run()
