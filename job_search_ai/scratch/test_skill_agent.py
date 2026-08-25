# -*- coding: utf-8 -*-

def test_skill_generation():
    import frappe
    import json
    from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
    from job_search_ai.agents.skill_agent.schemas import SkillRequest

    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    agent = SkillAgent()
    role = "Web Frontend Engineer"
    print(f"Generating skills for role: {role}...")
    
    req = SkillRequest(role=role, seniority="Junior")
    result = agent.run(req, save_to_doctype=False)
    
    print("\n--- GENERATED SKILLS PROFILE ---")
    print("Role:", result.profile.role_name)
    print("Foundation:", result.profile.foundation_skills)
    print("Core Domain:", result.profile.core_domain_skills)
    print("Industry:", result.profile.industry_skills)
    print("Emerging:", result.profile.emerging_skills)
