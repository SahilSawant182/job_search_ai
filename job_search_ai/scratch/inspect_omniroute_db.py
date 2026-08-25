import sqlite3

def run():
    print("=== OMNIROUTE DB TABLES ===")
    conn = sqlite3.connect("/home/dev/.omniroute/storage.sqlite")
    cursor = conn.cursor()
    
    tables_to_dump = ["provider_connections", "combos", "domain_fallback_chains"]
    for t in tables_to_dump:
        print(f"\n--- {t} ---")
        cursor.execute(f"SELECT * FROM {t}")
        rows = cursor.fetchall()
        for r in rows:
            print(r)
            
    conn.close()

if __name__ == "__main__":
    run()
