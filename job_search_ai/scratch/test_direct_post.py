import urllib.request
import json
import traceback

def run():
    url = "http://localhost:20128/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer any_token"
    }
    data = {
        "model": "career-agent",
        "messages": [
            {"role": "system", "content": "JSON only."},
            {"role": "user", "content": "Return a JSON object with a key 'message' and value 'Hello from OmniRoute!'"}
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"}
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    print("Sending POST request to OmniRoute career-agent combo...")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            status = response.status
            body = response.read().decode("utf-8")
            print(f"Status: {status}")
            print("Response body:")
            print(body)
    except Exception as e:
        print("Error:")
        print(e)
        if hasattr(e, "read"):
            try:
                print("Error body:")
                print(e.read().decode("utf-8"))
            except Exception as read_err:
                print("Could not read error body:", read_err)
        traceback.print_exc()

if __name__ == "__main__":
    run()
