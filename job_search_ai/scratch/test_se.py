import frappe
from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
from job_search_ai.agents.skill_agent.schemas import SkillRequest

def run():
    agent = SkillAgent()
    request = SkillRequest(role="Software Engineer")
    res = agent.run(request, save_to_doctype=False)
    print("=== SKILL AGENT RESULT FOR SOFTWARE ENGINEER ===")
    print(res.profile.as_dict() if hasattr(res.profile, "as_dict") else res.profile)
