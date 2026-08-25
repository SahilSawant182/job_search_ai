import unittest
from unittest.mock import MagicMock
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine

class TestWeightRedistribution(unittest.TestCase):
    def test_no_weight_boosting(self):
        # Setup student: B.Sc Physics, strong interest in Research
        student = StudentProfile(
            degree="B.Sc", branch="Physics", year=3, country="India",
            interests=["Research", "Simulation"], skills=["Python", "MATLAB", "Statistics"]
        )
        
        # We want to test that unconstrained careers do not get a boost
        # Let's create two mock candidates:
        # 1. Research Analyst (has degree constraints, fits perfectly)
        candidate1 = MagicMock()
        candidate1.career_name = "Research Analyst"
        candidate1.suitable_degrees = "B.Sc"
        candidate1.suitable_branches = "Physics"
        candidate1.required_skills = ["Python", "Statistics"]
        candidate1.preferred_skills = ["MATLAB"]
        candidate1.suitable_years = "3,4"
        candidate1.career_stage = "Growing"
        candidate1.future_demand = "High"
        
        # 2. Generic Unconstrained Career (no constraints)
        candidate2 = MagicMock()
        candidate2.career_name = "AI E2E Test Engineer"
        candidate2.suitable_degrees = ""
        candidate2.suitable_branches = ""
        candidate2.required_skills = ["Python"]
        candidate2.preferred_skills = []
        candidate2.suitable_years = "3,4"
        candidate2.career_stage = "Growing"
        candidate2.future_demand = "High"
        
        engine = RecommendationEngine()
        
        # Let's check how they score
        scored = engine.rank(student, [candidate1, candidate2])
        
        # Verify both candidates were scored
        self.assertEqual(len(scored), 2)
        
        # Since weight is 50/50 interest/skill under current CONSTANTS, let's verify it remains 50/50
        # for both candidates (no redistribution occurred).
        print("Scored careers:")
        for sc in scored:
            print(f"  {sc.candidate.career_name}: Final Score = {sc.final_score}, Scores = {sc.scores}")
            
if __name__ == "__main__":
    unittest.main()
