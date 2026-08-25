import urllib.request
import json

def run():
    url = "http://localhost:20128/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            models = [m['id'] for m in data.get('data', [])]
            for m in sorted(models):
                if 'groq' in m.lower():
                    print(m)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    run()
