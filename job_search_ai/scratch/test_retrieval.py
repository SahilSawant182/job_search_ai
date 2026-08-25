import frappe
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
from job_search_ai.services.settings_service import SettingsService

def run_test():
    settings = SettingsService.get()
    retriever = KnowledgeRetriever(settings=settings)
    
    # 1. Test direct retrieval
    student = StudentProfile(
        degree="B.Tech",
        branch="Civil Engineering",
        year=3,
        country="India",
        interests=["Construction"],
        skills=[]
    )
    print("Search text built:", retriever._build_search_text(student))
    
    try:
        r = retriever.retrieve(student)
        print("Retrieved records:", r)
    except Exception as e:
        print("Retrieval failed:", e)

if __name__ == "__main__":
    run_test()
