import os
import sys
import json
from unittest.mock import patch

# Change directory to bench root to allow frappe initialization
os.chdir('/home/dev/frappe-bench')
sys.path.append('/home/dev/frappe-bench/apps/frappe')
sys.path.append('/home/dev/frappe-bench/apps/nexedu')
sys.path.append('/home/dev/frappe-bench/apps/job_search_ai')

import frappe
frappe.init(site='devstridenex.quantcloud.in', sites_path='sites')
frappe.connect()

from job_search_ai.agents.roadmap_agent.agent import RoadmapAgent
from job_search_ai.services.skill_gap.service import SkillGapService
from nexedu.path_finder.api.path_enrollment import enroll_student

mock_response = {
    "career": "AI E2E Test Engineer",
    "milestones": [
        {
            "sequence": 1,
            "title": "Mastering Frappe API Development",
            "type": "Learn",
            "skill": "Frappe API Development",
            "skill_tier": "Foundation",
            "duration_days": 14,
            "objective": "Build robust backend endpoints using Frappe Framework.",
            "project": "Build custom REST endpoints and hook handlers.",
            "linked_resource_type": "Course",
            "linked_resource": "Frappe API Course 101"
        },
        {
            "sequence": 2,
            "title": "Jinja Templating Basics",
            "type": "Learn",
            "skill": "Jinja Templating",
            "skill_tier": "Foundation",
            "duration_days": 10,
            "objective": "Learn Jinja templating engine for document templates.",
            "project": "Design custom print format using Jinja.",
            "linked_resource_type": "Course",
            "linked_resource": "Jinja Templating Course 101"
        },
        {
            "sequence": 3,
            "title": "Python Programming in Frappe",
            "type": "Learn",
            "skill": "Python Programming",
            "skill_tier": "Foundation",
            "duration_days": 15,
            "objective": "Write Python scripts and server scripts in Frappe.",
            "project": "Create standard document script validation.",
            "linked_resource_type": "Course",
            "linked_resource": "Python Course 101"
        },
        {
            "sequence": 4,
            "title": "ERP System Integration Project",
            "type": "Build",
            "skill": "Frappe ERP Integration",
            "skill_tier": "Core Domain",
            "duration_days": 21,
            "objective": "Integrate third-party services and customize ERPNext modules.",
            "project": "Build a custom app to sync external orders with ERPNext sales orders.",
            "linked_resource_type": "Project",
            "linked_resource": "ERP Custom App Project"
        },
        {
            "sequence": 5,
            "title": "Webhooks Integration",
            "type": "Build",
            "skill": "Webhooks",
            "skill_tier": "Emerging",
            "duration_days": 10,
            "objective": "Configure and trigger Webhooks.",
            "project": "Build a webhook receiver to sync Slack updates.",
            "linked_resource_type": "Project",
            "linked_resource": "Webhook Custom App Project"
        },
        {
            "sequence": 6,
            "title": "Integrations Implementation",
            "type": "Build",
            "skill": "Integrations",
            "skill_tier": "Core Domain",
            "duration_days": 14,
            "objective": "Integrate system modules.",
            "project": "Create custom REST integration module.",
            "linked_resource_type": "Project",
            "linked_resource": "Integration App Project"
        },
        {
            "sequence": 7,
            "title": "AI-Assisted Workflow Automation",
            "type": "Build",
            "skill": "AI-Assisted Workflow Automation",
            "skill_tier": "Core Domain",
            "duration_days": 15,
            "objective": "Design workflow automation.",
            "project": "Integrate workflow with AI assistant trigger.",
            "linked_resource_type": "Project",
            "linked_resource": "AI Automation App Project"
        },
        {
            "sequence": 8,
            "title": "ERP AI Agents Validation",
            "type": "Assess",
            "skill": "AI Agents for ERP Workflows",
            "skill_tier": "Industry",
            "duration_days": 10,
            "objective": "Conduct comprehensive assessment of AI agent capabilities in ERP workflows.",
            "project": "Write automation test scripts validating agent actions on Frappe models.",
            "linked_resource_type": "Assessment",
            "linked_resource": "ERP AI Agent Assessment"
        },
        {
            "sequence": 9,
            "title": "LLM Integration with Frappe",
            "type": "Learn",
            "skill": "LLM Integration with Frappe",
            "skill_tier": "Industry",
            "duration_days": 15,
            "objective": "Learn to use LLM APIs inside Frappe backend.",
            "project": "Write a server script calling LLM to summarize document notes.",
            "linked_resource_type": "Course",
            "linked_resource": "LLM Frappe Course 101"
        },
        {
            "sequence": 10,
            "title": "ERP Automation Live Mentoring",
            "type": "Connect",
            "skill": "AI-assisted ERP Automation",
            "skill_tier": "Emerging",
            "duration_days": 5,
            "objective": "Connect with an ERP automation expert to review integration designs.",
            "project": "Present custom app architecture to mentor.",
            "linked_resource_type": "Mentor Session",
            "linked_resource": "Mentor Session ERP Automation"
        }
    ]
}

test_skills = [
    "Frappe API Development", "Jinja Templating", "Python Programming", 
    "Frappe ERP Integration", "Integrations", "AI-Assisted Workflow Automation", 
    "AI Agents for ERP Workflows", "LLM Integration with Frappe", "Webhooks", 
    "AI-assisted ERP Automation"
]

def run_e2e_test():
    student_email = "e2e_personalized_student@example.com"
    career_path_name = "AI E2E Test Engineer"
    existing_course = "Frappe API Course 101"
    
    print("=== STARTING END-TO-END PERSONALIZED ROADMAP TEST ===")
    
    # 1. SETUP / CLEANUP
    print("1. Setting up test student, skills, and career knowledge...")
    frappe.db.delete("Student Path Enrollment", {"student": student_email})
    frappe.db.delete("Student Skill", {"student": student_email})
    frappe.db.delete("Student", {"name": student_email})
    frappe.delete_doc("Career Knowledge", career_path_name, ignore_missing=True, force=True)
    frappe.delete_doc("Career Path", career_path_name, ignore_missing=True, force=True)
    
    # Create test skills
    for s in test_skills:
        if not frappe.db.exists("Skill", s):
            frappe.get_doc({"doctype": "Skill", "skill_name": s}).insert(ignore_permissions=True)
            
    # Create Career Knowledge
    ck_doc = frappe.get_doc({
        "doctype": "Career Knowledge",
        "career_name": career_path_name,
        "industry": "Technology",
        "active": 1,
        "skills": [
            {"skill_name": "Frappe API Development", "skill_type": "Required"},
            {"skill_name": "Jinja Templating", "skill_type": "Required"},
            {"skill_name": "Python Programming", "skill_type": "Required"},
            {"skill_name": "Frappe ERP Integration", "skill_type": "Required"},
            {"skill_name": "Webhooks", "skill_type": "Preferred"},
            {"skill_name": "Integrations", "skill_type": "Required"},
            {"skill_name": "AI-Assisted Workflow Automation", "skill_type": "Required"},
            {"skill_name": "AI Agents for ERP Workflows", "skill_type": "Preferred"},
            {"skill_name": "LLM Integration with Frappe", "skill_type": "Preferred"},
            {"skill_name": "AI-assisted ERP Automation", "skill_type": "Preferred"}
        ]
    })
    ck_doc.insert(ignore_permissions=True)

    # Create one existing course to test correct linking behavior
    if not frappe.db.exists("Courses", existing_course):
        frappe.db.sql("INSERT INTO `tabCourses` (name, course_name) VALUES (%s, %s)", (existing_course, existing_course))
        frappe.db.commit()
            
    # Get a college
    college = frappe.db.get_value("College", {}, "name")
    if not college:
        col = frappe.get_doc({"doctype": "College", "college_name": "Test College"})
        col.insert(ignore_permissions=True)
        college = col.name
        
    student = frappe.get_doc({
        "doctype": "Student",
        "first_name": "E2E",
        "last_name": "Personalized",
        "email_id": student_email,
        "college": college
    })
    student.insert(ignore_permissions=True)
    frappe.db.commit()
    
    print(f"Student {student_email} set up successfully with necessary Skill records.")
    
    # 2. RUN SKILL GAP
    print("\n2. Computing Skill Gap Report...")
    gap_service = SkillGapService()
    gap_report = gap_service.get_skill_gap_report(student_email, career_path_name)
    gap_dict = gap_report.to_dict()
    print("Skill Gap calculated:")
    print(f"  Matched Skills: {gap_report.matched_skills}")
    print(f"  Missing Foundation: {gap_report.missing_foundation}")
    print(f"  Missing Core Domain: {gap_report.missing_core_domain}")
    print(f"  Missing Industry: {gap_report.missing_industry}")
    print(f"  Missing Emerging: {gap_report.missing_emerging}")
    
    # 3. RUN ROADMAP AGENT & VALIDATION
    print("\n3. Running Roadmap Agent (Mocked LLM Response)...")
    with patch("job_search_ai.agents.roadmap_agent.llm_service.LLMService.call_agent", return_value=json.dumps(mock_response)):
        agent = RoadmapAgent()
        result = agent.run(student_email, career_path_name, gap_dict)
    
    print(f"Roadmap Agent finished. Validation Status: {result.validation_status}")
    if result.error_message:
        print(f"Validation Error: {result.error_message}")
        
    # Get database counts BEFORE enrollment
    counts_before = {
        "Courses": frappe.db.count("Courses"),
        "Project": frappe.db.count("Project"),
        "Assessment": frappe.db.count("Assessment"),
        "Internship": frappe.db.count("Internship"),
        "Mentor Session Booking": frappe.db.count("Mentor Session Booking")
    }
    print(f"\nDatabase counts BEFORE enrollment: {counts_before}")

    # 4. ENROLLMENT (Persisting to database)
    print("\n4. Performing student enrollment with AI personalized milestones...")
    try:
        with patch("job_search_ai.agents.roadmap_agent.llm_service.LLMService.call_agent", return_value=json.dumps(mock_response)):
            enroll_res = enroll_student(
                student=student_email,
                career_path=career_path_name,
                force_enroll=1,
                path_generation_mode="AI"
            )
        print(f"Enrollment Result: {enroll_res}")
        
        # Get database counts AFTER enrollment
        counts_after = {
            "Courses": frappe.db.count("Courses"),
            "Project": frappe.db.count("Project"),
            "Assessment": frappe.db.count("Assessment"),
            "Internship": frappe.db.count("Internship"),
            "Mentor Session Booking": frappe.db.count("Mentor Session Booking")
        }
        print(f"Database counts AFTER enrollment: {counts_after}")

        # Check no pollution assertion
        for k in counts_before:
            assert counts_before[k] == counts_after[k], f"Pollution detected in {k} table! Count changed from {counts_before[k]} to {counts_after[k]}"
        print("Success: Verified that no new/fake master records (stubs) were created during enrollment.")

        # 5. FETCH & DISPLAY CREATED MILESTONES
        if enroll_res.get("status") == "success":
            enrollment_name = enroll_res.get("enrollment")
            enrollment = frappe.get_doc("Student Path Enrollment", enrollment_name)
            print(f"\nSuccessfully created Enrollment Record: {enrollment_name}")
            print(f"ai_recommended: {enrollment.ai_recommended}")
            print(f"Total milestones created: {len(enrollment.milestone_progress)}")
            
            print("\nMilestone Records:")
            linked_resources_count = 0
            missing_resources_count = 0
            for m in enrollment.milestone_progress:
                print(f"  - Order {m.milestone_order}: {m.milestone_title}")
                print(f"    Type: {m.milestone_type}")
                print(f"    Skill: {m.skill} ({m.skill_tier})")
                print(f"    Duration: {m.duration_days} days")
                print(f"    Objective: {m.objective}")
                print(f"    Project: {m.project}")
                print(f"    Resource: {m.linked_resource} (Type: {m.linked_resource_type}, Ref DocType: {m.reference_doctype})")
                
                # Check link validation exists in db
                if m.reference_doctype and m.linked_resource:
                    exists = frappe.db.exists(m.reference_doctype, m.linked_resource)
                    print(f"    [Link Verification] {m.reference_doctype}:{m.linked_resource} exists in DB: {bool(exists)}")
                    assert exists, f"Linked resource {m.reference_doctype}:{m.linked_resource} does not exist in DB!"
                    linked_resources_count += 1
                else:
                    print(f"    [Resource Handling] Handled safely without creating fake records")
                    assert m.reference_doctype is None, "reference_doctype should be None for missing resource"
                    assert m.linked_resource is None, "linked_resource should be None for missing resource"
                    missing_resources_count += 1
                    
            print(f"\nExisting resources successfully linked: {linked_resources_count}")
            print(f"Missing resources handled without fake records: {missing_resources_count}")
            print("\nE2E Personalized Roadmap Integration Test PASSED successfully!")
        else:
            print("\nE2E Personalized Roadmap Integration Test FAILED.")
    except Exception as e:
        print(f"\nE2E Personalized Roadmap Integration Test FAILED with Exception: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
    # 6. CLEANUP
    print("\n6. Cleaning up test data...")
    frappe.db.delete("Student Path Enrollment", {"student": student_email})
    frappe.db.delete("Student", {"name": student_email})
    for s in test_skills:
        frappe.db.delete("Skill", {"name": s})
    if frappe.db.exists("Courses", existing_course):
        frappe.delete_doc("Courses", existing_course, ignore_missing=True, force=True)
    frappe.delete_doc("Career Knowledge", career_path_name, ignore_missing=True, force=True)
    frappe.delete_doc("Career Path", career_path_name, ignore_missing=True, force=True)
    frappe.db.commit()
    print("Cleanup completed.")
    print("=== END-TO-END PERSONALIZED ROADMAP TEST FINISHED ===")

if __name__ == '__main__':
    run_e2e_test()
