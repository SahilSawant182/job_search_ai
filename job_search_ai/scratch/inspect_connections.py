import sqlite3
import json

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, provider, label, decryptedValue FROM credentials")
    rows = cursor.fetchall()
    print("ALL CREDENTIALS:")
    for row in rows:
        key_snippet = row[3][:10] + "..." if row[3] else "None"
        print(f"ID: {row[0]}, Provider: {row[1]}, Label: {row[2]}, Key: {key_snippet}")
    conn.close()

if __name__ == "__main__":
    run()
