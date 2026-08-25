import json

def run():
    log_path = '/home/dev/.omniroute/call_logs/2026-08-17/2026-08-17T12-19-11.915Z_1786969149526-8e0323.json'
    with open(log_path, 'r') as f:
        data = json.load(f)
    print("KEYS:", list(data.keys()))
    print("REQUEST BODY:")
    print(json.dumps(data.get("requestBody"), indent=2))
    print("RESPONSE BODY:")
    print(json.dumps(data.get("responseBody"), indent=2))
    print("CLIENT RESPONSE:")
    print(json.dumps(data.get("clientResponse"), indent=2))
    print("ERROR:", data.get("error"))

if __name__ == "__main__":
    run()
