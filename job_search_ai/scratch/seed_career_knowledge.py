import frappe
from job_search_ai.services.skill_gap.normalizer import normalize_skill

def seed_role(role_name, skills):
    print(f"Seeding {role_name}...")
    # Find existing or create new
    ck_name = frappe.db.get_value("Career Knowledge", {"career_name": role_name}, "name")
    if ck_name:
        doc = frappe.get_doc("Career Knowledge", ck_name)
        print(f"Found existing record {ck_name} for {role_name}")
    else:
        doc = frappe.new_doc("Career Knowledge")
        doc.career_name = role_name
        doc.industry = "Technology"
        doc.category = "Software Engineering"
        doc.confidence = 1.0
        doc.active = 1
        doc.insert(ignore_permissions=True)
        print(f"Created new record {doc.name} for {role_name}")

    # Clear existing skills
    doc.set("skills", [])
    
    # Add new skills
    for s in skills:
        canonical_name = normalize_skill(s)
        # Check if already added to avoid duplicates
        if any(normalize_skill(child.skill_name) == canonical_name for child in doc.skills):
            continue
        doc.append("skills", {
            "skill_name": canonical_name,
            "skill_type": "Required"
        })
        
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"Successfully saved {role_name} with {len(doc.skills)} skills.")

def main():
    backend_skills = [
        "Python", "SQL", "Git", "RESTful APIs", "PostgreSQL",
        "Django", "Flask", "FastAPI", "Docker", "Redis",
        "Amazon Web Services"
    ]
    devops_skills = [
        "Git", "Linux Command Line", "Networking Basics", "Bash Scripting",
        "Docker", "Kubernetes", "Terraform", "Ansible",
        "GitHub Actions", "CI/CD", "Prometheus", "Grafana",
        "Amazon Web Services"
    ]
    frappe_skills = [
        "Python", "Git", "JavaScript", "SQL", "Frappe Framework",
        "MariaDB", "Redis", "RESTful APIs", "Frappe ORM",
        "ERPNext", "TailwindCSS", "Webhooks", "Amazon Web Services"
    ]
    
    seed_role("Backend Developer", backend_skills)
    seed_role("DevOps Engineer", devops_skills)
    seed_role("Frappe Developer", frappe_skills)

if __name__ == "__main__":
    frappe.connect()
    main()
