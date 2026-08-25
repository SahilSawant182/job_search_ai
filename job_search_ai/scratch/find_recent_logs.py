import os
import json

def run():
    log_dir = '/home/dev/.omniroute/call_logs/2026-08-17/'
    files = sorted([f for f in os.listdir(log_dir) if f.endswith('.json')])
    # print the last 15 files
    for filename in files[-15:]:
        filepath = os.path.join(log_dir, filename)
        with open(filepath, 'r') as f:
            data = json.load(f)
        summary = data.get('summary', {})
        print(f"File: {filename}")
        print(f"  ComboName: {summary.get('comboName')}")
        print(f"  ComboStepId: {summary.get('comboStepId')}")
        print(f"  RequestedModel: {summary.get('requestedModel')}")
        print(f"  Model: {summary.get('model')}")
        print(f"  Provider: {summary.get('provider')}")
        print(f"  Status: {summary.get('status')}")
        print(f"  Error: {data.get('error')}")
        print("-" * 50)

if __name__ == "__main__":
    run()
