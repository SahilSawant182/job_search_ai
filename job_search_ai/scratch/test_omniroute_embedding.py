import os
from openai import OpenAI

def run():
    # Fetch API key
    import frappe
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()
    
    api_key = frappe.conf.get("omniroute_api_key") or os.getenv("OMNIROUTE_API_KEY") or ""
    base_url = "http://localhost:20128/v1"
    
    print(f"Connecting to OmniRoute at {base_url} with api_key: {'***' if api_key else 'none'}...")
    client = OpenAI(base_url=base_url, api_key=api_key)
    
    try:
        # Try to call embeddings with a standard model
        resp = client.embeddings.create(
            input="quality assurance",
            model="text-embedding-3-small"
        )
        print("Success! Embedding dimensions:", len(resp.data[0].embedding))
    except Exception as e:
        print("Failed to get embedding from OmniRoute:", e)

if __name__ == "__main__":
    run()
