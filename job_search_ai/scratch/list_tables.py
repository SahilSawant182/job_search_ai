import sqlite3

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables:")
    for t in tables:
        print("-", t[0])
    conn.close()

if __name__ == "__main__":
    run()
