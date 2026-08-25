import urllib.request
import json

def run():
    print("=== INSPECTING OMNIROUTE MODELS ===")
    try:
        req = urllib.request.Request("http://localhost:20128/v1/models")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id") or m.get("name") for m in data.get("data", [])]
            print("Available models:")
            for m in models:
                print(f"  - {m}")
    except Exception as e:
        print("Failed to query OmniRoute:", str(e))

if __name__ == "__main__":
    run()
