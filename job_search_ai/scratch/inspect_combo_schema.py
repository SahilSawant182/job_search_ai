import sqlite3
import json

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(combos)")
    cols = cursor.fetchall()
    print("COMBO TABLE COLUMNS:")
    for col in cols:
        print(f"- {col[1]} ({col[2]})")
    
    cursor.execute("SELECT * FROM combos WHERE name='career-agent'")
    row = cursor.fetchone()
    if row:
        print("\nCAREER-AGENT ROW:")
        for idx, col in enumerate(cols):
            val = row[idx]
            if col[1] == 'data' and val:
                print(f"data (parsed):\n{json.dumps(json.loads(val), indent=2)}")
            else:
                print(f"{col[1]}: {val}")
    conn.close()

if __name__ == "__main__":
    run()
