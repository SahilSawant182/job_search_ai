import json
import frappe
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever, RetrievedKnowledge
from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine

def trace_career(career_name_query):
    # Find matching Career Knowledge doc
    docs = frappe.get_all(
        "Career Knowledge",
        filters={"career_name": ["like", f"%{career_name_query}%"], "active": 1},
        fields=["name", "career_name"]
    )
    if not docs:
        print(f"Career not found for query: {career_name_query}")
        return
    
    doc_name = docs[0]["name"]
    doc = frappe.get_doc("Career Knowledge", doc_name)
    
    # Trace skills in DB
    db_req = [s.skill_name for s in doc.skills if (s.skill_type or "Required") == "Required"]
    db_pref = [s.skill_name for s in doc.skills if (s.skill_type or "Required") in ("Preferred", "Advanced")]
    
    # Simulate retriever parsing (RetrievedKnowledge object creation)
    all_skills = [s.skill_name for s in doc.skills]
    retrieved = RetrievedKnowledge(
        doc_name=doc.name,
        similarity=1.0,
        hybrid_score=1.0,
        career_name=doc.career_name or "",
        skills=all_skills,
        required_skills=db_req,
        advanced_skills=db_pref,
        preferred_skills=db_pref,
        nice_skills=[s.skill_name for s in doc.skills if (s.skill_type or "Required") not in ("Required", "Preferred", "Advanced")],
        companies=[],
        quality_score=int(doc.quality_score or 70),
        evidence_count=1
    )
    
    # Setup a mock student profile that has all required skills to calculate a score
    student = StudentProfile(
        degree="B.Tech",
        branch="Computer Science",
        year=4,
        country="India",
        interests=[doc.career_name],
        skills=db_req + db_pref # Give student all skills
    )
    
    # Recommendation engine scoring
    engine = RecommendationEngine()
    req_list, pref_list = engine._get_candidate_skills(retrieved)
    skill_score, debug_dict = engine._score_skills(student, retrieved)
    
    print(f"Career: {doc.career_name} ({doc.name})")
    print(f"  DB count           : Required={len(db_req)}, Preferred={len(db_pref)}")
    print(f"  Retriever slots    : Required={len(retrieved.required_skills)}, Preferred={len(retrieved.preferred_skills)}")
    print(f"  Engine get_skills  : Required={len(req_list)}, Preferred={len(pref_list)}")
    print(f"  Scoring (full match): Score={skill_score:.4f}, Matched Req={len(debug_dict['matched_req'])}, Matched Pref={len(debug_dict['matched_pref'])}")
    print("-" * 80)

def main():
    careers = [
        "AI Engineer",
        "Frontend Developer",
        "Backend Developer",
        "DevOps Engineer",
        "Financial Analyst",
        "Frappe Developer",
        "Cybersecurity Specialist",
        "Product Designer",
        "Data Scientist",
        "Employee Experience Manager"
    ]
    for c in careers:
        trace_career(c)

if __name__ == "__main__":
    main()
