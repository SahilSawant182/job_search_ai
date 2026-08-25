import os
import json

def run():
    log_dir = '/home/dev/.omniroute/call_logs/2026-08-17/'
    if not os.path.exists(log_dir):
        print("Log dir doesn't exist")
        return
    
    for filename in os.listdir(log_dir):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(log_dir, filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            summary = data.get('summary', {})
            if summary.get('status') == 200 and 'deepseek-v4-flash' in str(summary.get('requestedModel')):
                print(f"File: {filename}")
                print(f"Requested Model: {summary.get('requestedModel')}")
                print(f"ResponseBody key count/type: {type(data.get('responseBody'))}")
                print("responseBody snippet:", str(data.get('responseBody'))[:500])
                print("-" * 50)
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if __name__ == "__main__":
    run()
