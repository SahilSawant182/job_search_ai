import requests
import json

def run():
    print("=== TESTING GROQ DIRECT CALL ===")
    
    api_key = "YOUR_GROQ_API_KEY_HERE"
    base_url = "https://api.groq.com/openai/v1"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    models = ["groq/compound", "groq/compound-mini"]
    
    for model in models:
        print(f"\nTesting Groq model: {model}")
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Return JSON: {\"status\": \"ok\"}"}],
                    "temperature": 0.2,
                    "max_tokens": 100
                },
                timeout=10,
            )
            print(f"Status Code: {resp.status_code}")
            if resp.status_code == 200:
                print("Response:", resp.json()["choices"][0]["message"]["content"])
            else:
                print("Error:", resp.text)
        except Exception as e:
            print("Failed:", str(e))

if __name__ == "__main__":
    run()
