# -*- coding: utf-8 -*-
import frappe
from datetime import datetime

# Default skills to seed if they do not exist
DEFAULT_SKILLS = [
    # Technology / Engineering
    {
        "skill_name": "Python",
        "category": "Programming Language",
        "domain": "Software Engineering",
        "description": "High-level, general-purpose programming language widely used in AI, web, and scripting.",
        "aliases": ["py", "python3", "python 3"]
    },
    {
        "skill_name": "JavaScript",
        "category": "Programming Language",
        "domain": "Software Engineering",
        "description": "A lightweight, interpreted programming language with first-class functions for the web.",
        "aliases": ["js", "es6", "javascript ES6"]
    },
    {
        "skill_name": "TypeScript",
        "category": "Programming Language",
        "domain": "Software Engineering",
        "description": "A strongly typed programming language that builds on JavaScript, giving you better tooling at any scale.",
        "aliases": ["ts", "typescript language"]
    },
    {
        "skill_name": "Java",
        "category": "Programming Language",
        "domain": "Software Engineering",
        "description": "Class-based, object-oriented programming language designed to have as few implementation dependencies as possible.",
        "aliases": ["java programming", "jdk"]
    },
    {
        "skill_name": "React",
        "category": "Frontend Framework",
        "domain": "Software Engineering",
        "description": "A JavaScript library for building user interfaces, developed by Meta.",
        "aliases": ["react.js", "reactjs", "react-js"]
    },
    {
        "skill_name": "Node.js",
        "category": "Backend Runtime",
        "domain": "Software Engineering",
        "description": "An open-source, cross-platform JavaScript runtime environment.",
        "aliases": ["nodejs", "node.js runtime", "node"]
    },
    {
        "skill_name": "Next.js",
        "category": "Web Framework",
        "domain": "Software Engineering",
        "description": "A React framework for production, offering SSR, static generation, and routing.",
        "aliases": ["nextjs", "next.js framework"]
    },
    {
        "skill_name": "Spring Boot",
        "category": "Backend Framework",
        "domain": "Software Engineering",
        "description": "An open-source Java-based framework used to create microservices and standalone production-ready spring applications.",
        "aliases": ["springboot", "spring-boot"]
    },
    {
        "skill_name": "Docker",
        "category": "DevOps / Containerization",
        "domain": "Software Engineering",
        "description": "A set of platform-as-a-service products that use OS-level virtualization to deliver software in packages called containers.",
        "aliases": ["docker containers", "dockerfile"]
    },
    {
        "skill_name": "Kubernetes",
        "category": "DevOps / Orchestration",
        "domain": "Software Engineering",
        "description": "An open-source container orchestration system for automating software deployment, scaling, and management.",
        "aliases": ["k8s", "k8s cluster"]
    },
    {
        "skill_name": "TensorFlow",
        "category": "Machine Learning Framework",
        "domain": "Artificial Intelligence",
        "description": "A free and open-source software library for machine learning and artificial intelligence.",
        "aliases": ["tf", "tensorflow library"]
    },
    {
        "skill_name": "SQL",
        "category": "Database Language",
        "domain": "Software Engineering",
        "description": "Structured Query Language used for managing data in relational databases.",
        "aliases": ["mysql", "postgresql", "sqlite", "sql language", "mariadb"]
    },
    {
        "skill_name": "HTML",
        "category": "Web Technology",
        "domain": "Software Engineering",
        "description": "HyperText Markup Language is the standard markup language for documents designed to be displayed in a web browser.",
        "aliases": ["html5", "xhtml"]
    },
    {
        "skill_name": "CSS",
        "category": "Web Technology",
        "domain": "Software Engineering",
        "description": "Cascading Style Sheets is a stylesheet language used for describing the presentation of a document written in a markup language.",
        "aliases": ["css3", "sass", "scss", "tailwind"]
    },
    {
        "skill_name": "Express",
        "category": "Backend Framework",
        "domain": "Software Engineering",
        "description": "Minimal and flexible Node.js web application framework.",
        "aliases": ["express.js", "expressjs"]
    },
    # Design
    {
        "skill_name": "Figma",
        "category": "UI/UX Design Tool",
        "domain": "Design",
        "description": "A collaborative web application for interface design.",
        "aliases": ["figma tool", "figma mockup"]
    },
    {
        "skill_name": "AutoCAD",
        "category": "CAD Software",
        "domain": "Design / Engineering",
        "description": "Computer-aided design software that architects, engineers, and construction professionals rely on to create precise 2D and 3D drawings.",
        "aliases": ["autocad 2d", "autocad 3d"]
    },
    # Business / Commerce
    {
        "skill_name": "Excel",
        "category": "Spreadsheet Tool",
        "domain": "Commerce / Business",
        "description": "A spreadsheet developed by Microsoft for Windows, macOS, Android, and iOS.",
        "aliases": ["microsoft excel", "ms excel", "spreadsheets"]
    },
    {
        "skill_name": "Financial Analysis",
        "category": "Finance Method",
        "domain": "Commerce / Business",
        "description": "The process of evaluating businesses, projects, budgets, and other finance-related transactions to determine their performance and suitability.",
        "aliases": ["financial modeling", "corporate finance", "accounting"]
    },
    # CAD / Civil / Mechanical
    {
        "skill_name": "SolidWorks",
        "category": "CAD Software",
        "domain": "Mechanical Engineering",
        "description": "A solid modeling computer-aided design and computer-aided engineering computer program.",
        "aliases": ["solidworks cad", "3d modeling"]
    },
    {
        "skill_name": "MATLAB",
        "category": "Numerical Computing",
        "domain": "Engineering",
        "description": "A proprietary multi-paradigm programming language and numeric computing environment.",
        "aliases": ["matlab script", "simulink"]
    },
    {
        "skill_name": "Algorithms",
        "category": "Tech Skill",
        "domain": "Software Engineering",
        "description": "A set of rules or instructions step-by-step to solve a problem.",
        "aliases": ["algo", "algorithms list"]
    }
]

def seed_skills():
    """Seed the default skills and their aliases into the database.
    Migrates static mappings in DEFAULT_CANONICAL_ALIASES to DB.

    Returns the number of new skills inserted.
    """
    from job_search_ai.services.skill_gap.normalizer import DEFAULT_CANONICAL_ALIASES, get_skill_key
    print(f"Seeding default skills and aliases into database...")
    count = 0

    # 1. Seed DEFAULT_SKILLS
    for s_info in DEFAULT_SKILLS:
        skill_name = s_info["skill_name"]
        try:
            if not frappe.db.exists("Skill Master", skill_name):
                doc = frappe.new_doc("Skill Master")
                doc.skill_name = skill_name
                doc.category = s_info["category"]
                doc.domain = s_info["domain"]
                doc.description = s_info["description"]
                doc.active = 1
                doc.last_updated = datetime.now()
                doc.insert(ignore_permissions=True)
                count += 1
            else:
                doc = frappe.get_doc("Skill Master", skill_name)

            # Ensure aliases exist
            updated = False
            for alias in s_info.get("aliases", []):
                if not alias or alias.lower().strip() == skill_name.lower().strip():
                    continue
                # Check if alias is already present
                alias_exists = False
                for row in getattr(doc, "aliases", []):
                    if row.alias.lower().strip() == alias.lower().strip():
                        alias_exists = True
                        break
                if not alias_exists:
                    doc.append("aliases", {
                        "alias": alias,
                        "canonical_skill": skill_name
                    })
                    updated = True
            if updated:
                doc.save(ignore_permissions=True)
        except Exception as exc:
            print(f"Failed to seed skill {skill_name}: {exc}")

    # 2. Seed DEFAULT_CANONICAL_ALIASES from normalizer
    for alias, canonical in DEFAULT_CANONICAL_ALIASES.items():
        if not alias or not canonical:
            continue
        try:
            # Ensure canonical skill exists in Skill Master
            if not frappe.db.exists("Skill Master", canonical):
                doc = frappe.new_doc("Skill Master")
                doc.skill_name = canonical
                doc.category = "Tech Skill"
                doc.domain = "Software Engineering"
                doc.active = 1
                doc.last_updated = datetime.now()
                doc.insert(ignore_permissions=True)
                count += 1
            else:
                doc = frappe.get_doc("Skill Master", canonical)

            if alias.lower().strip() != canonical.lower().strip():
                # Check if alias exists in parent aliases
                alias_exists = False
                for row in getattr(doc, "aliases", []):
                    if row.alias.lower().strip() == alias.lower().strip():
                        alias_exists = True
                        break
                if not alias_exists:
                    doc.append("aliases", {
                        "alias": alias,
                        "canonical_skill": canonical
                    })
                    doc.save(ignore_permissions=True)
        except Exception as exc:
            print(f"Failed to seed alias mapping {alias} -> {canonical}: {exc}")

    # 3. Seed DEFAULT_RELATIONSHIPS
    DEFAULT_RELATIONSHIPS = [
        {
            "from_skill": "DSA",
            "relation_type": "Contains",
            "to_skill": "Data Structures",
            "confidence": 1.0,
            "source_type": "Manual",
            "is_trusted_source": 1,
            "status": "Approved",
            "active": 1
        },
        {
            "from_skill": "DSA",
            "relation_type": "Contains",
            "to_skill": "Algorithms",
            "confidence": 1.0,
            "source_type": "Manual",
            "is_trusted_source": 1,
            "status": "Approved",
            "active": 1
        },
        {
            "from_skill": "GitHub",
            "relation_type": "Contains",
            "to_skill": "Git",
            "confidence": 1.0,
            "source_type": "Manual",
            "is_trusted_source": 1,
            "status": "Approved",
            "active": 1
        },
        {
            "from_skill": "Probability Theory",
            "relation_type": "Alias",
            "to_skill": "Probability",
            "confidence": 1.0,
            "source_type": "Manual",
            "is_trusted_source": 1,
            "status": "Approved",
            "active": 1
        }
    ]

    for rel in DEFAULT_RELATIONSHIPS:
        try:
            # Ensure both skill masters exist first
            for sk in [rel["from_skill"], rel["to_skill"]]:
                if not frappe.db.exists("Skill Master", sk):
                    # We can create a simple skill master
                    doc_sm = frappe.new_doc("Skill Master")
                    doc_sm.skill_name = sk
                    doc_sm.category = "Tech Skill"
                    doc_sm.domain = "Software Engineering"
                    doc_sm.active = 1
                    doc_sm.insert(ignore_permissions=True)
            
            # Check if relationship already exists
            if not frappe.db.exists("Skill Relationship", {"from_skill": rel["from_skill"], "to_skill": rel["to_skill"], "relation_type": rel["relation_type"]}):
                doc_rel = frappe.new_doc("Skill Relationship")
                doc_rel.update(rel)
                doc_rel.insert(ignore_permissions=True)
        except Exception as exc:
            print(f"Failed to seed relationship {rel['from_skill']} -> {rel['to_skill']}: {exc}")

    frappe.db.commit()
    # Invalidate caches to ensure new seed is loaded
    try:
        from job_search_ai.services.skill_gap.normalizer import invalidate_normalization_cache
        invalidate_normalization_cache()
    except Exception:
        pass
    try:
        from job_search_ai.services.skill_gap.relationship import invalidate_relationship_cache
        invalidate_relationship_cache()
    except Exception:
        pass

    print(f"Successfully seeded/migrated skills/aliases.")
    return count
