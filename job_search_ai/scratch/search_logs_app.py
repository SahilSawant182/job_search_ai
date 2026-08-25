import re

def run():
    log_path = '/home/dev/.omniroute/logs/application/app.log'
    with open(log_path, 'r') as f:
        lines = f.readlines()
    
    # print the last 20 matching lines
    matches = []
    for line in lines:
        if 'quality' in line.lower() or 'failed quality' in line.lower() or 'exhausted' in line.lower():
            matches.append(line.strip())
            
    print(f"Total matches: {len(matches)}")
    for m in matches[-30:]:
        print(m)

if __name__ == "__main__":
    run()
