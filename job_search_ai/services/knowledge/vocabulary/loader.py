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
    }
]

def seed_skills():
    """Seed the default skills and their aliases into the database if the Skill Master table is empty.

    Returns the number of skills inserted.
    """
    existing_count = frappe.db.count("Skill Master")
    if existing_count > 0:
        return 0

    print(f"Seeding {len(DEFAULT_SKILLS)} default skills into Skill Master...")
    count = 0
    for s_info in DEFAULT_SKILLS:
        try:
            # Create Skill Master doc (insert first so link validation passes)
            doc = frappe.new_doc("Skill Master")
            doc.skill_name = s_info["skill_name"]
            doc.category = s_info["category"]
            doc.domain = s_info["domain"]
            doc.description = s_info["description"]
            doc.active = 1
            doc.last_updated = datetime.now()
            doc.insert(ignore_permissions=True)

            # Now add aliases and save
            for alias in s_info.get("aliases", []):
                doc.append("aliases", {
                    "alias": alias,
                    "canonical_skill": s_info["skill_name"]
                })
            
            doc.save(ignore_permissions=True)
            count += 1
        except Exception as exc:
            print(f"Failed to seed skill {s_info['skill_name']}: {exc}")

    frappe.db.commit()
    print(f"Successfully seeded {count} skills.")
    return count
