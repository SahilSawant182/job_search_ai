import frappe
import traceback

def run():
    frappe.init(site="devstridenex.quantcloud.in", sites_path="/home/dev/frappe-bench/sites")
    frappe.connect()
    
    from nexedu.api.skill_assessment_ai import _llm_chat, LLM_PROVIDER
    
    print("LLM Provider is configured to:", LLM_PROVIDER)
    
    prompt = "Return a JSON object with a key 'message' and value 'Hello from OmniRoute!'"
    print("Calling _llm_chat with prompt...")
    
    try:
        response = _llm_chat(prompt)
        print("Response received:")
        print(response)
    except Exception as e:
        print("Error during LLM chat:")
        print(e)
        traceback.print_exc()

if __name__ == "__main__":
    run()
