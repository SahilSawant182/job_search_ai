def run():
    log_path = '/home/dev/.omniroute/logs/application/app.log'
    with open(log_path, 'r') as f:
        lines = f.readlines()
    
    matches = []
    for line in lines:
        if 'validate quality error' in line.lower():
            matches.append(line.strip())
            
    print(f"Total validation error matches: {len(matches)}")
    for m in matches[-10:]:
        print(m)

if __name__ == "__main__":
    run()
