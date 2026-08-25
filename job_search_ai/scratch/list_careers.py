import frappe

def run():
    frappe.init(site="devstridenex.quantcloud.in", sites_path="../../sites")
    frappe.connect()
    
    careers = frappe.get_all("Career Knowledge", fields=["name", "career_name", "country"])
    print(f"Total careers: {len(careers)}")
    for c in careers:
        print(f"  {c['name']}: {c['career_name']} ({c.get('country')})")

if __name__ == "__main__":
    run()
