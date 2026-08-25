import os
import sys
import logging

# Set up paths and initialize Frappe
os.chdir('/home/dev/frappe-bench')
sys.path.append('/home/dev/frappe-bench/apps/frappe')
sys.path.append('/home/dev/frappe-bench/apps/nexedu')
sys.path.append('/home/dev/frappe-bench/apps/job_search_ai')

import frappe
frappe.init(site='devstridenex.quantcloud.in', sites_path='sites')
frappe.connect()

# Set up logging to stdout to see everything
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from job_search_ai.agents.career_trend import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.agents.career_trend.profile_recommendation_knowledge import ProfileRecommendationKnowledge

# Mock lookup to force MISS
ProfileRecommendationKnowledge.lookup = lambda self, student: None

student = StudentProfile(
    degree="B.Tech",
    branch="Computer Science",
    year=3,
    country="India",
    interests=["Web Development", "Artificial Intelligence"],
    skills=["Python"]
)

agent = CareerTrendAgent()
res = agent.run(student)
print("\n=== AGENT RESPONSE ===")
print(res.to_dict())
print("Metrics:", getattr(res, "metrics", {}))
