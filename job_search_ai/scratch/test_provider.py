import frappe
from nexedu.api.skill_assessment_ai import _get_active_provider, _get_active_model
from job_search_ai.services.settings_service import SettingsService

def run():
    print("frappe.local.initialised:", getattr(frappe.local, "initialised", None))
    print("Job Search AI Settings llm_provider:", frappe.db.get_single_value("Job Search AI Settings", "llm_provider"))
    print("_get_active_provider():", _get_active_provider())
    print("_get_active_model('ollama'):", _get_active_model("ollama"))
    
    settings = SettingsService.get()
    print("SettingsService llm_provider:", settings.llm_provider)
    print("SettingsService default_llm_model:", settings.default_llm_model)

if __name__ == "__main__":
    frappe.connect()
    run()
