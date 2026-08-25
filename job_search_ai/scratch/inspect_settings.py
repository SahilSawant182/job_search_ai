import frappe

def run():
    print("=== INSPECTING SETTINGS ===")
    settings = frappe.get_single("Job Search AI Settings")
    print("llm_provider:", settings.llm_provider)
    print("default_llm_model:", settings.default_llm_model)
    print("ollama_endpoint:", settings.ollama_endpoint)
    print("omniroute_base_url:", settings.omniroute_base_url)
    print("omniroute_model:", settings.omniroute_model)
    print("llm_timeout_seconds:", settings.llm_timeout_seconds)
    print("retry_count:", settings.retry_count)

if __name__ == "__main__":
    run()
