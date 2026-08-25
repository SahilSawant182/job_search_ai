import frappe
from job_search_ai.services.settings_service import SettingsService

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()
    settings = SettingsService.get()
    print("LLM Provider:", settings.llm_provider)
    print("OmniRoute Base URL:", settings.omniroute_base_url)
    print("OmniRoute Model:", settings.omniroute_model)
    print("Default LLM Model:", settings.default_llm_model)
    print("Ollama Endpoint:", settings.ollama_endpoint)
    print("LLM Timeout Seconds:", settings.llm_timeout_seconds)
    print("Retry Count:", settings.retry_count)
    print("Qdrant URL:", settings.qdrant_url)
    print("Qdrant Collection Name:", settings.qdrant_collection_name)
    
if __name__ == "__main__":
    run()
