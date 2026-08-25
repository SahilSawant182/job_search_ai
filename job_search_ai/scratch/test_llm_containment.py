import unittest
import frappe
from job_search_ai.agents.career_trend.schemas import CareerRecommendation
from job_search_ai.agents.career_trend.llm_service import LLMService

class TestLLMContainment(unittest.TestCase):
    def test_containment(self):
        # Setup inputs
        input_candidates = [
            CareerRecommendation(
                career="Machine Learning Engineer", category="Tech", confidence=80, why_for_you="",
                career_stage="Growing", future_demand="High", industry="Technology"
            ),
            CareerRecommendation(
                career="Analytics Specialist", category="Tech", confidence=70, why_for_you="",
                career_stage="Growing", future_demand="High", industry="Technology"
            ),
            CareerRecommendation(
                career="Quantitative Analyst", category="Finance", confidence=60, why_for_you="",
                career_stage="Growing", future_demand="High", industry="Finance"
            )
        ]
        
        # Simulated LLM raw output (parsed JSON)
        raw_llm_json = {
            "strategy": "Simulated strategy.",
            "recommended_paths": [
                {"career": "AI Agent Developer", "why_for_you": "Hallucinated"},
                {"career": "Machine Learning Engineer", "why_for_you": "Ground truth matched"},
                {"career": "Agricultural Data Scientist", "why_for_you": "Hallucinated"},
                {"career": "Analytics Specialist", "why_for_you": "Fuzzy matched Specialist"}
            ]
        }
        
        # Instantiate LLMService (model name doesn't matter for _parse_response)
        service = LLMService(model_name="dummy")
        
        # Execute parsing
        result = service._parse_response(raw_llm_json, input_candidates)
        
        # Verify
        recs = result.recommended_paths
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0].career, "Machine Learning Engineer")
        self.assertEqual(recs[0].why_for_you, "Ground truth matched")
        self.assertEqual(recs[1].career, "Analytics Specialist")
        self.assertEqual(recs[1].why_for_you, "Fuzzy matched Specialist")
        
        print("Test passed! Only original candidate careers survived, in the correct order.")

if __name__ == "__main__":
    unittest.main()
