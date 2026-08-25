import os
with open("/home/dev/frappe-bench/logs/web.error.log", "r") as f:
    lines = f.readlines()
    for line in lines[-50:]:
        print(line.strip())
