import sqlite3

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(provider_connections)")
    columns = cursor.fetchall()
    print("Columns:")
    for col in columns:
        print(f"- {col[1]} ({col[2]})")
    
    cursor.execute("SELECT * FROM provider_connections")
    rows = cursor.fetchall()
    print("\nRows:")
    for row in rows:
        print(row)
    conn.close()

if __name__ == "__main__":
    run()
