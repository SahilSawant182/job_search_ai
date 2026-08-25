import sqlite3
import json
import uuid
from datetime import datetime, UTC

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if already exists
    cursor.execute("SELECT id FROM combos WHERE name='omniroute_test_model'")
    row = cursor.fetchone()
    if row:
        print("Combo omniroute_test_model already exists with ID:", row[0])
        conn.close()
        return
        
    # Create the combo dict
    combo_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    
    combo_data = {
        "name": "omniroute_test_model",
        "description": "OmniRoute Test Model Routing",
        "models": [
            {
                "id": f"omniroute-test-model-groq-llama-3.3-70b-versatile-{combo_id}",
                "kind": "model",
                "model": "groq/llama-3.3-70b-versatile",
                "providerId": "groq",
                "connectionId": "53364dc5-1356-4afe-a89d-fc2614e6a620",
                "weight": 0,
                "label": "Groq-Main"
            }
        ],
        "strategy": "priority",
        "config": {
            "maxRetries": 1,
            "retryDelayMs": 2000,
            "handoffThreshold": 0.85,
            "handoffModel": "",
            "maxMessagesForSummary": 30,
            "trackMetrics": True,
            "reasoningTokenBufferEnabled": True,
            "zeroLatencyOptimizationsEnabled": False
        },
        "id": combo_id,
        "isHidden": False,
        "sortOrder": 2,
        "createdAt": now_iso,
        "updatedAt": now_iso,
        "version": 1
    }
    
    cursor.execute(
        "INSERT INTO combos (id, name, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (combo_id, "omniroute_test_model", json.dumps(combo_data), now_iso, now_iso)
    )
    conn.commit()
    print("Inserted combo omniroute_test_model successfully with ID:", combo_id)
    conn.close()

if __name__ == "__main__":
    run()
