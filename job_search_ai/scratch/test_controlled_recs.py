# -*- coding: utf-8 -*-
import frappe
import time
from datetime import datetime, timezone
from job_search_ai.agents.career_trend.agent import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile, CareerTrendResponse
from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine

def run_controlled_test():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    agent = CareerTrendAgent()
    engine = RecommendationEngine()

    print("====================================================")
    print("1. RUNNING PROFILES A, B, C, D TO PROVE WEIGHTING")
    print("====================================================")

    # Profile A: Skills = Python, SQL | Interests = Machine Learning Engineer
    profile_a = StudentProfile(
        degree="B.Tech", branch="Computer Science", year=3, country="India",
        skills=["Python", "SQL"],
        interests=["Machine Learning Engineer"]
    )

    # Profile B: Skills = Python, SQL | Interests = Frontend Developer
    profile_b = StudentProfile(
        degree="B.Tech", branch="Computer Science", year=3, country="India",
        skills=["Python", "SQL"],
        interests=["Frontend Developer"]
    )

    # Profile C: Skills = HTML, CSS, JavaScript, Git | Interests = Machine Learning Engineer
    profile_c = StudentProfile(
        degree="B.Tech", branch="Computer Science", year=3, country="India",
        skills=["HTML", "CSS", "JavaScript", "Git"],
        interests=["Machine Learning Engineer"]
    )

    # Profile D: Skills = HTML, CSS, JavaScript, Git | Interests = Frontend Developer
    profile_d = StudentProfile(
        degree="B.Tech", branch="Computer Science", year=3, country="India",
        skills=["HTML", "CSS", "JavaScript", "Git"],
        interests=["Frontend Developer"]
    )

    res_a = agent.run(profile_a)
    print(f"\n[Profile A] Skills: Python/SQL | Interests: ML Engineer")
    for r in res_a.recommended_paths:
        print(f"  -> Recommended: {r.career} (Confidence: {r.confidence}%)")

    res_b = agent.run(profile_b)
    print(f"\n[Profile B] Skills: Python/SQL | Interests: Frontend Developer")
    for r in res_b.recommended_paths:
        print(f"  -> Recommended: {r.career} (Confidence: {r.confidence}%)")

    res_c = agent.run(profile_c)
    print(f"\n[Profile C] Skills: HTML/CSS/JS/Git | Interests: ML Engineer")
    for r in res_c.recommended_paths:
        print(f"  -> Recommended: {r.career} (Confidence: {r.confidence}%)")

    res_d = agent.run(profile_d)
    print(f"\n[Profile D] Skills: HTML/CSS/JS/Git | Interests: Frontend Developer")
    for r in res_d.recommended_paths:
        print(f"  -> Recommended: {r.career} (Confidence: {r.confidence}%)")

    print("\n====================================================")
    print("2. PROVING THE 50/50 FORMULA NUMERICALLY")
    print("====================================================")
    
    # We will fetch and score a candidate directly to print the raw scoring weights
    # ML Engineer in MariaDB
    docs_ml = frappe.get_all("Career Knowledge", filters={"career_name": "Machine Learning Engineer", "active": 1}, fields=["name"])
    # Frontend Developer in MariaDB
    docs_fe = frappe.get_all("Career Knowledge", filters={"career_name": "Frontend Developer", "active": 1}, fields=["name"])
    
    from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
    retriever = KnowledgeRetriever()
    
    class _MetadataHit:
        def __init__(self, doc_id: str):
            self.id = doc_id
            self.score = 0.5

    def print_formula_check(label, student, doc_name):
        retrieved_k = retriever._load_from_mariadb([_MetadataHit(doc_name)], student)
        if retrieved_k:
            scored = engine.rank(student, retrieved_k)
            if scored:
                sc = scored[0]
                career = sc.candidate.career_name
                interest_score = sc.scores["interest_match"]
                skill_score = sc.scores["skill_match"]
                final_score = sc.final_score
                expected_score = 0.5 * interest_score + 0.5 * skill_score
                diff = abs(final_score - expected_score)
                print(f"[{label}] Career: {career}")
                print(f"  -> Interest Match Score: {interest_score:.4f}")
                print(f"  -> Skill Match Score:    {skill_score:.4f}")
                print(f"  -> Final Score:          {final_score:.4f}")
                print(f"  -> Expected (0.5*I + 0.5*S): {expected_score:.4f} (Diff: {diff:.6f})")
                assert diff < 0.001, "Formula deviation is too large!"
                print("  => Formula Match: SUCCESS")

    if docs_ml:
        print_formula_check("Profile A vs ML Engineer", profile_a, docs_ml[0]["name"])
        print_formula_check("Profile C vs ML Engineer", profile_c, docs_ml[0]["name"])
    if docs_fe:
        print_formula_check("Profile B vs Frontend Developer", profile_b, docs_fe[0]["name"])
        print_formula_check("Profile D vs Frontend Developer", profile_d, docs_fe[0]["name"])

    print("\n====================================================")
    print("3. PROVING KNOWLEDGE HIT (SIMILAR PROFILE PATTERN)")
    print("====================================================")

    # Let's create Profile A_similar which is 80%+ similar to Profile A:
    # A has skills=["Python", "SQL"] and interests=["Machine Learning Engineer"]
    # A_similar has skills=["python", "sql", "git"] and interests=["Machine Learning Engineer"]
    profile_a_similar = StudentProfile(
        degree="B.Tech", branch="Computer Science", year=3, country="India",
        skills=["python", "sql", "git"],
        interests=["Machine Learning Engineer"]
    )

    t0 = time.perf_counter()
    res_a_sim = agent.run(profile_a_similar)
    t_duration = time.perf_counter() - t0
    
    is_hit = res_a_sim.metrics.get("knowledge_hit") if hasattr(res_a_sim, "metrics") and res_a_sim.metrics else False
    print(f"A_similar profile Knowledge HIT: {is_hit}")
    print(f"Execution time: {t_duration * 1000:.1f}ms")
    print(f"LLM time: {res_a_sim.metrics.get('llm_response_time', 0) * 1000:.1f}ms")
    print(f"Tavily used: {res_a_sim.metrics.get('tavily_used', False)}")
    print(f"Model Name used: {res_a_sim.metrics.get('model_name')}")
    print("Recommendations returned:")
    for r in res_a_sim.recommended_paths:
         print(f"  -> {r.career} (Confidence: {r.confidence}%)")

    print("\n====================================================")
    print("4. DISSIMILAR PROFILE MISS PROOF")
    print("====================================================")
    
    # Profile E: completely different skills and interests
    profile_e = StudentProfile(
        degree="B.Tech", branch="Computer Science", year=3, country="India",
        skills=["React", "Tailwind CSS"],
        interests=["Full Stack Developer"]
    )

    t0 = time.perf_counter()
    res_e = agent.run(profile_e)
    t_duration = time.perf_counter() - t0

    is_hit_e = res_e.metrics.get("knowledge_hit") if hasattr(res_e, "metrics") and res_e.metrics else False
    print(f"Dissimilar Profile E Cache/Knowledge HIT: {is_hit_e}")
    print(f"Execution time: {t_duration:.2f} seconds")

    print("\n====================================================")
    print("5. CACHE COLLISION & POLLUTION TEST")
    print("====================================================")
    # Search with a profile similar in keywords but representing different interests
    # Profile F: Skills = Python, SQL | Interests = Frontend Developer
    # We want to verify it does NOT hit ML Engineer or Frontend Developer cached responses
    # because of cosine vector score alone.
    from job_search_ai.agents.career_trend.profile_recommendation_knowledge import ProfileRecommendationKnowledge
    from job_search_ai.services.settings_service import SettingsService
    settings = SettingsService.get()
    rec_knowledge = ProfileRecommendationKnowledge(settings)

    hit_f = rec_knowledge.lookup(profile_b)
    print(f"Lookup of Profile B (Python/SQL + Frontend Developer) HIT: {hit_f is not None}")
    if hit_f:
        print(f"  -> Matched pattern interests: {hit_f.get('interests')}")
        print(f"  -> Matched pattern skills: {hit_f.get('skills')}")
        print(f"  -> Matched careers: {hit_f.get('career_paths')}")
        print(f"  -> Combined Similarity: {hit_f.get('combined_similarity')}")

    # Verify no student identity fields are stored in the Qdrant payload:
    # We check the payload fields returned
    if hit_f:
        invalid_keys = {"student", "student_id", "email", "name", "cgpa", "university"}
        intersect = invalid_keys.intersection(hit_f.keys())
        print(f"Private details found in payload: {list(intersect)}")
        assert len(intersect) == 0, "Security violation: student private details stored!"
    else:
        print("No private details checked (Lookup was a correct MISS).")

    print("\n====================================================")
    print("6. PERSISTENCE TEST (PROCESS RESTART SIMULATION)")
    print("====================================================")
    # Simulate process restart by instantiating a completely new agent and cache context
    new_agent = CareerTrendAgent()
    t0 = time.perf_counter()
    new_res = new_agent.run(profile_a_similar)
    t_duration = time.perf_counter() - t0
    
    new_is_hit = new_res.metrics.get("knowledge_hit") if hasattr(new_res, "metrics") and new_res.metrics else False
    print(f"New Agent Instance - Knowledge HIT: {new_is_hit}")
    print(f"New Instance Execution time: {t_duration * 1000:.1f}ms")
    print(f"New Instance LLM time: {new_res.metrics.get('llm_response_time', 0) * 1000:.1f}ms")
    print(f"New Instance Tavily used: {new_res.metrics.get('tavily_used', False)}")

if __name__ == "__main__":
    run_controlled_test()
