import frappe
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
from job_search_ai.services.settings_service import SettingsService
from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine

def run_test():
    settings = SettingsService.get()
    retriever = KnowledgeRetriever(settings=settings)
    engine = RecommendationEngine()
    
    student = StudentProfile(
        degree="B.Tech",
        branch="Civil Engineering",
        year=3,
        country="India",
        interests=["Construction"],
        skills=[]
    )
    
    retrieved = retriever.retrieve(student)
    scored = engine.rank(student, retrieved)
    
    print("Scored results:")
    for sc in scored[:5]:
        print(f"Career: {sc.candidate.career_name} | Final Score: {sc.final_score} | Raw Sim: {sc.candidate.similarity} | Scores: {sc.scores} | Reason Codes: {sc.reason_codes}")

if __name__ == "__main__":
    run_test()
