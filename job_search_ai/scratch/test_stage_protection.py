import unittest
from unittest.mock import MagicMock
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine

class TestStageProtection(unittest.TestCase):
    def test_stage_protection_penalties(self):
        engine = RecommendationEngine()
        
        # Test Case 1: Year 1 Student + Manager Career
        student1 = StudentProfile(
            degree="B.Tech", branch="Computer Science", year=1, country="India",
            interests=["Software Development"], skills=["HTML", "CSS", "JavaScript"]
        )
        
        manager_career = MagicMock()
        manager_career.career_name = "Web Development Manager"
        manager_career.career_stage = "Managerial"
        manager_career.suitable_degrees = "B.Tech"
        manager_career.suitable_branches = "Computer Science"
        manager_career.required_skills = ["HTML", "CSS", "JavaScript"]
        manager_career.preferred_skills = []
        manager_career.suitable_years = "3,4"
        manager_career.future_demand = "High"
        
        dev_career = MagicMock()
        dev_career.career_name = "Frontend Developer"
        dev_career.career_stage = "Entry"
        dev_career.suitable_degrees = "B.Tech"
        dev_career.suitable_branches = "Computer Science"
        dev_career.required_skills = ["HTML", "CSS", "JavaScript"]
        dev_career.preferred_skills = []
        dev_career.suitable_years = "1,2,3,4"
        dev_career.future_demand = "High"
        
        scored = engine.rank(student1, [manager_career, dev_career])
        
        # The frontend developer should be ranked above the manager
        self.assertEqual(scored[0].candidate.career_name, "Frontend Developer")
        self.assertLess(scored[1].final_score, scored[0].final_score)
        
        print("Scored list for Year 1 student:")
        for sc in scored:
            print(f"  {sc.candidate.career_name}: Final Score = {sc.final_score}, Reason Codes = {sc.reason_codes}")

if __name__ == "__main__":
    unittest.main()
