import frappe
import groq

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()
    api_key = frappe.conf.get("groq_api_key")
    client = groq.Groq(api_key=api_key)
    try:
        r = client.chat.completions.create(
            model="groq/compound-mini",
            messages=[{"role": "user", "content": "Return a JSON object containing the key 'status' with value 'ok'. Output ONLY the JSON."}],
            response_format={"type": "json_object"},
            timeout=30,
        )
        print("Response:")
        print(r.choices[0].message.content)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    run()
