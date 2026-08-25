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
        # print the models key specifically
        print(json.dumps(data.get("models"), indent=2))
        # print the rest of the combo config
        for k, v in data.items():
            if k != "models":
                print(f"{k}: {v}")
    conn.close()

if __name__ == "__main__":
    run()
