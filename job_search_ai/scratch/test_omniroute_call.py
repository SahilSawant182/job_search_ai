import requests
import frappe

def run():
    print("=== TESTING OMNIROUTE CALLS WITH MAX_TOKENS ===")
    
    api_key = None
    if frappe.local and getattr(frappe.local, "initialised", False):
        api_key = frappe.conf.get("omniroute_api_key")
    if not api_key:
        api_key = "my_test_omniroute_key"
        
    base_url = "http://localhost:20128/v1"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    models = ["omniroute_test_model", "career-agent"]
    
    for model in models:
        print(f"\nTesting model: {model}")
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Return JSON: {\"status\": \"ok\"}"}],
                    "temperature": 0.2,
                    "max_tokens": 1000,
                    "stream": False
                },
                timeout=10,
            )
            print(f"Status Code: {resp.status_code}")
            print("Raw text:", resp.text)
        except Exception as e:
            print("Failed:", str(e))

if __name__ == "__main__":
    run()
