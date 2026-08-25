import frappe

def run():
    print("=== INSPECTING RECENT ERROR LOGS ===")
    logs = frappe.get_all(
        "Error Log",
        fields=["name", "method", "creation", "error"],
        order_by="creation desc",
        limit=5
    )
    for l in logs:
        print(f"Name: {l.name} | Method: {l.method} | Created: {l.creation}")
        print(f"Error:\n{l.error[:500]}...")
        print("-" * 60)
