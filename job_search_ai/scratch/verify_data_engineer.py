import frappe

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()
    
    from job_search_ai.agents.skill_agent.doctype_writer import _resolve_job_profile
    ck_name = _resolve_job_profile("AI Engineer")
    print("CK Name:", ck_name)
    if ck_name:
        skills = frappe.db.sql(
            "SELECT skill_name, skill_type FROM `tabCareer Knowledge Skill` WHERE parent = %s",
            (ck_name,),
            as_dict=True
        )
        print("Skills:")
        for s in skills:
            print(f"  {s['skill_name']} ({s['skill_type']})")
