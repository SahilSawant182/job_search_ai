import sqlite3
import json

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, data FROM combos WHERE name = 'career-agent'")
    row = cursor.fetchone()
    if row:
        print("Name:", row[0])
        print("Data:")
        data = json.loads(row[1])
        print(json.dumps(data, indent=2))
    else:
        print("No combo named career-agent found!")
        # Let's list all combos
        cursor.execute("SELECT name FROM combos")
        rows = cursor.fetchall()
        print("All combos:", [r[0] for r in rows])
    conn.close()

if __name__ == "__main__":
    run()
