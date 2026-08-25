import frappe

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()
    
    settings_doc = frappe.get_doc("Job Search AI Settings")
    print("Settings fields:")
    for k, v in settings_doc.as_dict().items():
        if v:
            print(f"  {k}: {v}")

if __name__ == "__main__":
    run()
