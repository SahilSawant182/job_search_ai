import json

def run():
    path = '/home/dev/.omniroute/call_logs/2026-08-17/2026-08-17T12-02-33.777Z_1786968150241-cc1633.json'
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            # Print response body details
            body = data.get('responseBody')
            print("responseBody type:", type(body))
            print("responseBody string representation:")
            print(json.dumps(body, indent=2))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    run()
