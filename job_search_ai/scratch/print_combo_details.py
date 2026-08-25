import sqlite3
import json

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT data FROM combos WHERE name='career-agent'")
    row = cursor.fetchone()
    if row:
        data = json.loads(row[0])
        print(json.dumps(data, indent=2))
    else:
        print("Not found")
    conn.close()

if __name__ == "__main__":
    run()
