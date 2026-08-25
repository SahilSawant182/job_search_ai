import sqlite3
import json

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get column names
    cursor.execute("PRAGMA table_info(call_logs)")
    columns = [c[1] for c in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM call_logs ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        for col, val in zip(columns, row):
            # Print excerpt
            print(f"{col}: {str(val)[:300]}...")
        print("-" * 50)
        
    conn.close()

if __name__ == "__main__":
    run()
