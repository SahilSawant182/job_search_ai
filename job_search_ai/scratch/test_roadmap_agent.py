import frappe
from job_search_ai.agents.roadmap_agent.agent import RoadmapAgent
from job_search_ai.agents.roadmap_agent.llm_service import LLMService

def run():
    print("=== TESTING ROADMAP AGENT ===")
    
    # 1. Inspect current settings
    settings = frappe.get_single('Job Search AI Settings')
    print(f"Current provider: {settings.llm_provider}")
    print(f"Ollama Endpoint: {settings.ollama_endpoint}")
    print(f"Ollama Model: {settings.default_llm_model}")
    print(f"OmniRoute Model: {settings.omniroute_model}")
    print(f"Timeout: {settings.llm_timeout_seconds}")
    
    # 2. Test LLMService initialization and a simple query
    try:
        print("\n--- Testing LLM call ---")
        service = LLMService()
        print(f"Initialized LLMService with provider: {service.provider}")
        res = service.call_agent("Hello! Return a JSON object with one key 'status' set to 'ok'.")
        print("Response:", res)
    except Exception as e:
        print("LLM Call Failed:", str(e))
        import traceback
        traceback.print_exc()
