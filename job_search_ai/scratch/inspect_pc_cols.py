import sqlite3

def run():
    conn = sqlite3.connect("/home/dev/.omniroute/storage.sqlite")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(provider_connections)")
    columns = [col[1] for col in cursor.fetchall()]
    print("provider_connections table columns:", columns)
    conn.close()

if __name__ == "__main__":
    run()
