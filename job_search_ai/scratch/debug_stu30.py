import frappe
from unittest.mock import patch
from job_search_ai.agents.career_trend.agent import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile

@patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed")
def debug(mock_embed):
    mock_embed.return_value = [0.1] * 768
    
    frappe.init(site="devstridenex.quantcloud.in", sites_path="../../sites")
    frappe.connect()
    
    student = StudentProfile(
        degree="BBA",
        branch="Entrepreneurship",
        year=4,
        country="India",
        interests=["Entrepreneurship", "Startups", "Business Strategy"],
        skills=["Business Planning", "Market Research", "Communication", "Financial Modeling"]
    )
    
    agent = CareerTrendAgent()
    res = agent.run(student)
    print("Recommended paths:", res.recommended_paths)
    print("Strategy:", res.strategy)

if __name__ == "__main__":
    debug()
