import frappe
import time
from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
from job_search_ai.agents.skill_agent.schemas import SkillRequest

def run():
    print("=== TESTING SKILL GENERATION ===")
    
    # Temporarily set timeout to 180 seconds to allow Ollama to complete
    settings = frappe.get_single('Job Search AI Settings')
    orig_timeout = settings.llm_timeout_seconds
    settings.llm_timeout_seconds = 180
    settings.save()
    frappe.db.commit()
    
    try:
        agent = SkillAgent()
        req = SkillRequest(role="Frappe Developer")
        
        t0 = time.time()
        print("Running SkillAgent for 'Frappe Developer'...")
        res = agent.run(req, save_to_doctype=False)
        t1 = time.time()
        
        print(f"Success in {t1 - t0:.2f} seconds!")
        print("Foundation Skills:", res.profile.foundation_skills)
        print("Core Domain Skills:", res.profile.core_domain_skills)
        print("Industry Skills:", res.profile.industry_skills)
        print("Emerging Skills:", res.profile.emerging_skills)
    except Exception as e:
        print("Failed:", str(e))
        import traceback
        traceback.print_exc()
    finally:
        # Restore timeout
        settings = frappe.get_single('Job Search AI Settings')
        settings.llm_timeout_seconds = orig_timeout
        settings.save()
        frappe.db.commit()
