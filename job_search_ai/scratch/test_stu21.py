import frappe
import time
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.agents.career_trend.agent import CareerTrendAgent

def run():
    agent = CareerTrendAgent()

    # The 3 profiles that failed with the old QueryBuilder
    profiles = [
        {
            "id": "STU029",
            "name": "Varun Operations",
            "student": StudentProfile(
                degree="BBA", branch="Operations Management", year=3, country="India",
                interests=["Operations", "Supply Chain", "Process Optimization"],
                skills=["Excel", "Supply Chain Basics", "Process Mapping", "Data Analysis"]
            )
        },
        {
            "id": "STU034",
            "name": "Kabir Content Creator",
            "student": StudentProfile(
                degree="BA", branch="Mass Communication", year=3, country="India",
                interests=["Content Creation", "Social Media", "Video Production"],
                skills=["Video Editing", "Content Writing", "Storytelling", "Social Media"]
            )
        },
        {
            "id": "STU035",
            "name": "Anjali Psychology",
            "student": StudentProfile(
                degree="BA", branch="Psychology", year=3, country="India",
                interests=["Psychology", "Mental Wellbeing", "Counselling"],
                skills=["Communication", "Psychological Assessment", "Counselling Basics", "Research"]
            )
        },
    ]

    for p in profiles:
        print(f"\n{'='*55}")
        print(f"Testing {p['id']}: {p['name']}")
        t0 = time.perf_counter()
        try:
            resp = agent.run(p["student"])
            elapsed = time.perf_counter() - t0
            careers = [r.career for r in resp.recommended_paths]
            print(f"  Status  : {'SUCCESS' if careers else 'EMPTY'}")
            print(f"  Careers : {careers}")
            print(f"  Time    : {elapsed:.2f}s")
            m = getattr(resp, 'metrics', {})
            print(f"  Tavily  : {m.get('tavily_used')}  Model: {m.get('model_name')}  KHit: {m.get('knowledge_hit')}")
        except Exception as e:
            import traceback
            traceback.print_exc()
