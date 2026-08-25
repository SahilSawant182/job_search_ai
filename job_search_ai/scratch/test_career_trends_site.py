# -*- coding: utf-8 -*-
import os
import sys

# Change directory to bench root to allow frappe initialization
os.chdir('/home/dev/frappe-bench')
sys.path.append('/home/dev/frappe-bench/apps/frappe')
sys.path.append('/home/dev/frappe-bench/apps/nexedu')
sys.path.append('/home/dev/frappe-bench/apps/job_search_ai')

import frappe
frappe.init(site='devstridenex.quantcloud.in', sites_path='sites')
frappe.connect()

import logging
logging.basicConfig(level=logging.INFO)

from job_search_ai.agents.career_trend import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile

def test_run():
    student = StudentProfile(
        degree="B.Tech",
        branch="Computer Science",
        year=3,
        country="India",
        interests=["Data Analitics", "Machine Learning"],
        skills=["Python", "Matplotlib", "Numpy", "Pandas", "PowerBI"]
    )
    
    agent = CareerTrendAgent()
    try:
        res = agent.run(student)
        print("RECOMMENDED PATHS:")
        for r in res.recommended_paths:
            print(f"  - {r.career} ({r.confidence}%) - {r.why_for_you}")
        print("STRATEGY:", res.strategy)
        print("METRICS:", res.metrics)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_run()
