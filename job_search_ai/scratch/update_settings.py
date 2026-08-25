import frappe

def run():
    print("=== UPDATE SETTINGS ===")
    settings = frappe.get_single("Job Search AI Settings")
    settings.llm_provider = "omniroute"
    settings.omniroute_model = "omniroute_test_model"
    settings.llm_timeout_seconds = 180
    settings.save()
    frappe.db.commit()
    print("Settings updated successfully!")

if __name__ == "__main__":
    run()
