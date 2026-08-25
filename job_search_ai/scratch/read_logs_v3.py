import os
print("=== WEB ERROR LOG ===")
if os.path.exists("/home/dev/frappe-bench/logs/web.error.log"):
    with open("/home/dev/frappe-bench/logs/web.error.log", "r") as f:
        lines = f.readlines()
        for line in lines[-30:]:
            print(line.strip())

print("\n=== FRAPPE LOG ===")
if os.path.exists("/home/dev/frappe-bench/logs/frappe.log"):
    with open("/home/dev/frappe-bench/logs/frappe.log", "r") as f:
        lines = f.readlines()
        for line in lines[-30:]:
            print(line.strip())
