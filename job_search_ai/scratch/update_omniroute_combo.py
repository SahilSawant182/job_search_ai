import sqlite3
import json

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, data FROM combos WHERE id='78272131-a9f9-4b49-a7a3-434fe5947a31'")
    row = cursor.fetchone()
    if not row:
        print("Combo not found!")
        return
        
    combo_id, data_str = row
    config = json.loads(data_str)
    
    models = config.get('models', [])
    print("Original models order:")
    for m in models:
        print(f"- {m.get('label')}: {m.get('model')}")
        
    # Reorder so that openrouter is first
    openrouter_models = [m for m in models if m.get('providerId') == 'openrouter']
    other_models = [m for m in models if m.get('providerId') != 'openrouter']
    
    new_models = openrouter_models + other_models
    config['models'] = new_models
    
    new_data_str = json.dumps(config)
    cursor.execute("UPDATE combos SET data=? WHERE id=?", (new_data_str, combo_id))
    conn.commit()
    print("\nUpdated models order successfully!")
    
    # Verify
    cursor.execute("SELECT data FROM combos WHERE id=?", (combo_id,))
    updated_data_str = cursor.fetchone()[0]
    updated_config = json.loads(updated_data_str)
    print("Verified updated models order:")
    for m in updated_config.get('models', []):
        print(f"- {m.get('label')}: {m.get('model')}")
        
    conn.close()

if __name__ == "__main__":
    run()
