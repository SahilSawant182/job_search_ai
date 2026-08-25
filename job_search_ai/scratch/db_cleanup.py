import frappe

def clean_database():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    print("=== Database Cleanup Started ===")

    # 1. Delete orphan rows from Prerequisite Skills where parent does not exist
    print("Cleaning up Prerequisite Skills...")
    orphans_prereqs = frappe.db.sql("""
        SELECT name FROM `tabPrerequisite Skills`
        WHERE parent NOT IN (SELECT name FROM `tabCareer Path`)
    """, as_dict=True)
    if orphans_prereqs:
        print(f"Found {len(orphans_prereqs)} orphan Prerequisite Skills rows. Deleting...")
        frappe.db.sql("""
            DELETE FROM `tabPrerequisite Skills`
            WHERE parent NOT IN (SELECT name FROM `tabCareer Path`)
        """)
        frappe.db.commit()

    # 2. Delete orphan rows from Path Milestone where parent does not exist
    print("Cleaning up Path Milestones...")
    orphans_milestones = frappe.db.sql("""
        SELECT name FROM `tabPath Milestone`
        WHERE parent NOT IN (SELECT name FROM `tabCareer Path`)
    """, as_dict=True)
    if orphans_milestones:
        print(f"Found {len(orphans_milestones)} orphan Path Milestone rows. Deleting...")
        frappe.db.sql("""
            DELETE FROM `tabPath Milestone`
            WHERE parent NOT IN (SELECT name FROM `tabCareer Path`)
        """)
        frappe.db.commit()

    # 3. Clean up duplicate rows within existing Career Paths
    career_paths = frappe.get_all("Career Path", pluck="name")
    for cp in career_paths:
        print(f"Checking Career Path: {cp}")
        # Prerequisite Skills deduplication
        prereqs = frappe.get_all(
            "Prerequisite Skills",
            filters={"parent": cp},
            fields=["name", "prerequisite_skills"],
            order_by="idx asc"
        )
        seen_prereqs = set()
        for p in prereqs:
            skill_key = p.prerequisite_skills.lower().strip() if p.prerequisite_skills else ""
            if skill_key in seen_prereqs:
                print(f"Deleting duplicate Prerequisite Skill {p.prerequisite_skills} ({p.name}) in {cp}")
                frappe.db.delete("Prerequisite Skills", {"name": p.name})
            else:
                seen_prereqs.add(skill_key)

        # Path Milestone deduplication
        milestones = frappe.get_all(
            "Path Milestone",
            filters={"parent": cp},
            fields=["name", "skill"],
            order_by="idx asc"
        )
        seen_milestones = set()
        for m in milestones:
            skill_key = m.skill.lower().strip() if m.skill else ""
            if skill_key in seen_milestones:
                print(f"Deleting duplicate Path Milestone for skill {m.skill} ({m.name}) in {cp}")
                frappe.db.delete("Path Milestone", {"name": m.name})
            else:
                seen_milestones.add(skill_key)
        
        frappe.db.commit()

    # 4. Delete all Roadmap Templates to force regeneration
    print("Purging Roadmap Templates...")
    templates = frappe.get_all("Roadmap Template", pluck="name")
    for t in templates:
        print(f"Deleting Roadmap Template: {t}")
        frappe.delete_doc("Roadmap Template", t, ignore_permissions=True, force=True)
    frappe.db.commit()

    print("=== Database Cleanup Completed Successfully ===")

if __name__ == "__main__":
    clean_database()
