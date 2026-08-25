import sqlite3
import json

def run():
    conn = sqlite3.connect('/home/dev/.omniroute/storage.sqlite')
    cursor = conn.cursor()
    
    print("--- provider_connections ---")
    cursor.execute("SELECT * FROM provider_connections")
    for r in cursor.fetchall():
        print(r)
        
    print("\n--- combos ---")
    cursor.execute("SELECT * FROM combos")
    for r in cursor.fetchall():
        print(r)
        
    print("\n--- key_value ---")
    cursor.execute("SELECT * FROM key_value WHERE key LIKE '%model%' OR key LIKE '%provider%' LIMIT 20")
    for r in cursor.fetchall():
        print(r)
        
    conn.close()

if __name__ == "__main__":
    run()
