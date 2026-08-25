# -*- coding: utf-8 -*-
import frappe
import time
from job_search_ai.agents.career_trend.agent import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile

def test_cache_and_ranking():
    # Make sure we use a site context
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    agent = CareerTrendAgent()

    # 1. First run with a profile (Cache MISS expected, then stored in Qdrant)
    student1 = StudentProfile(
        degree="B.Tech",
        branch="Computer Science",
        year=3,
        country="India",
        interests=["Frontend Developer"],
        skills=["html", "css", "javascript", "git", "responsive design"]
    )
    
    print("\n--- RUN 1: Starting recommendation generation (Cache MISS expected) ---")
    start_time = time.perf_counter()
    response1 = agent.run(student1)
    duration1 = time.perf_counter() - start_time
    
    print(f"Run 1 completed in {duration1:.3f} seconds.")
    print("Strategy:", response1.strategy)
    print("Recommended Paths:")
    for path in response1.recommended_paths:
        print(f"  - {path.career} (Confidence: {path.confidence}%)")
        print(f"    Why: {path.why_for_you}")
        print(f"    Skills: {path.skills}")
    
    # 2. Second run with the exact same profile (Cache HIT expected, < 0.2 seconds)
    print("\n--- RUN 2: Repeating exact same profile (Cache HIT expected) ---")
    start_time = time.perf_counter()
    response2 = agent.run(student1)
    duration2 = time.perf_counter() - start_time
    
    print(f"Run 2 completed in {duration2:.3f} seconds.")
    is_hit = response2.metrics.get("knowledge_hit") if hasattr(response2, "metrics") and response2.metrics else False
    print(f"Cache HIT status: {is_hit}")
    print("Strategy:", response2.strategy)
    
    # 3. Third run with 80%+ similar profile (e.g. slight change in casing/whitespaces or minor interest/skill modification)
    student2 = StudentProfile(
        degree="B.Tech",
        branch="Computer Science",
        year=3,
        country="India",
        interests=["frontend developer"],
        skills=["HTML", "CSS", "JavaScript", "Git", "responsive design"]
    )
    
    print("\n--- RUN 3: Repeating with >80% similar profile (Cache HIT expected) ---")
    start_time = time.perf_counter()
    response3 = agent.run(student2)
    duration3 = time.perf_counter() - start_time
    
    print(f"Run 3 completed in {duration3:.3f} seconds.")
    is_hit3 = response3.metrics.get("knowledge_hit") if hasattr(response3, "metrics") and response3.metrics else False
    print(f"Cache HIT status: {is_hit3}")

if __name__ == "__main__":
    test_cache_and_ranking()
