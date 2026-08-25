import sqlite3

def run():
    db_path = '/home/dev/.omniroute/storage.sqlite'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(combos)")
    columns = [c[1] for c in cursor.fetchall()]
    print("Columns:", columns)
    
    cursor.execute("SELECT * FROM combos")
    rows = cursor.fetchall()
    for row in rows:
        for col, val in zip(columns, row):
            print(f"{col}: {str(val)[:200]}...")
            
    conn.close()

if __name__ == "__main__":
    run()
