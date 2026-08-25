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
            
            # Check if there is an error in this call log or if it corresponds to the fail times
            error_str = data.get('error', '') or ''
            summary = data.get('summary', {})
            summary_err = summary.get('error', '') or ''
            
            # If the log mentions "failed quality" or the status is 502/504
            if 'quality' in str(error_str).lower() or 'quality' in str(summary_err).lower() or data.get('status') in [502, 504]:
                print(f"File: {filename}")
                print(f"Status: {data.get('status')}")
                print(f"Model: {data.get('model')}")
                print(f"Requested Model: {data.get('requestedModel')}")
                print(f"Error: {error_str or summary_err}")
                print(f"ResponseBody type: {type(data.get('responseBody'))}")
                print("ResponseBody:", str(data.get('responseBody'))[:1000])
                print("=" * 60)
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if __name__ == "__main__":
    run()
