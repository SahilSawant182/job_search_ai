import sqlite3
import json

def run():
    print("=== FIXING OMNIROUTE DB ===")
    conn = sqlite3.connect("/home/dev/.omniroute/storage.sqlite")
    cursor = conn.cursor()
    
    # 1. Update combos
    cursor.execute("SELECT id, data FROM combos")
    combos = cursor.fetchall()
    for cid, config_str in combos:
        if not config_str:
            continue
        try:
            config = json.loads(config_str)
            updated = False
            # Check models list
            if "models" in config:
                for m in config["models"]:
                    if m.get("model") == "groq/compound":
                        m["model"] = "groq/groq/compound"
                        updated = True
                        print(f"Updated combo {config.get('name')} model to groq/groq/compound")
            if updated:
                new_config_str = json.dumps(config)
                cursor.execute("UPDATE combos SET data = ? WHERE id = ?", (new_config_str, cid))
        except Exception as e:
            print(f"Error parsing/updating combo {cid}: {e}")
            
    # 2. Update provider connections
    cursor.execute("""
        UPDATE provider_connections 
        SET test_status = 'active', error_code = NULL, last_error = NULL, rate_limited_until = NULL 
        WHERE provider = 'groq'
    """)
    print(f"Reset {cursor.rowcount} Groq provider connections to active")
    
    conn.commit()
    conn.close()
    print("Successfully committed changes to OmniRoute DB!")

if __name__ == "__main__":
    run()
