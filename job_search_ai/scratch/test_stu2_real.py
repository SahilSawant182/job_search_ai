# -*- coding: utf-8 -*-
import os
import sys

# Change directory to bench root to allow frappe initialization
os.chdir('/home/dev/frappe-bench')
sys.path.append('/home/dev/frappe-bench/apps/frappe')
sys.path.append('/home/dev/frappe-bench/apps/nexedu')
sys.path.append('/home/dev/frappe-bench/apps/job_search_ai')

import frappe
frappe.init(site='devstridenex.quantcloud.in', sites_path='sites')
frappe.connect()

import json
from nexedu.path_finder.app_api import get_recommended_paths, get_active_plan
from nexedu.path_finder.api.path_enrollment import enroll_student

def run_test():
    student_email = "stu2@gmail.com"
    target_skills = ["HTML", "CSS", "JavaScript", "React", "Node.js"]
    
    print(f"=== STARTING END-TO-END FLOW TEST FOR {student_email} ===")
    
    # Step 1: Clean up existing enrollments and skills to start fresh
    print("\n[Step 1] Cleaning up existing Student Path Enrollments and Student Skills...")
    frappe.db.delete("Student Path Enrollment", {"student": student_email})
    frappe.db.delete("Student Skill", {"student": student_email})
    frappe.db.commit()
    
    # Step 2: Declare student skills
    print(f"\n[Step 2] Declaring student skills: {target_skills}...")
    for s in target_skills:
        if not frappe.db.exists("Skill", s):
            frappe.get_doc({
                "doctype": "Skill",
                "skill_name": s
            }).insert(ignore_permissions=True)
            
        frappe.get_doc({
            "doctype": "Student Skill",
            "student": student_email,
            "skill": s,
            "current_level": "Intermediate",
            "self_declared": 1,
            "ai_verified": 1,
            "status": "Verified"
        }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("Skills declared successfully!")
    
    # Step 3: Fetch recommended paths
    print("\n[Step 3] Fetching path recommendations via CareerTrendAgent...")
    recommendations = get_recommended_paths(student_email)
    print(f"Recommendations count: {len(recommendations)}")
    if not recommendations:
        print("No recommendations returned! Creating a default recommendation 'Full Stack Developer'...")
        recommended_path = "Full Stack Developer"
    else:
        # Show top recommendations
        for idx, rec in enumerate(recommendations[:3]):
            print(f"  {idx+1}. Path: {rec['career_path']} | Fit Score: {rec['fit_score']}% | Match Count: {rec['matched_count']}")
        recommended_path = recommendations[0]['career_path']
        
    print(f"Selected Path to Enroll: {recommended_path}")

    # Create dummy active path to verify auto-pause logic
    dummy_path = "Python Developer"
    print(f"\n[Auto-Pause Verification] Creating dummy Active enrollment for '{dummy_path}'...")
    dummy_enrollment = frappe.get_doc({
        "doctype": "Student Path Enrollment",
        "student": student_email,
        "career_path": dummy_path,
        "status": "Active",
        "enrolled_at": frappe.utils.now_datetime()
    })
    dummy_enrollment.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"Dummy active enrollment created: {dummy_enrollment.name}")
    
    # Step 4: Run AI Enrollment (this triggers the real LLM-based RoadmapAgent)
    print(f"\n[Step 4] Enrolling student in '{recommended_path}' with AI personalized roadmap...")
    enroll_res = enroll_student(
        student=student_email,
        career_path=recommended_path,
        path_generation_mode="AI"
    )
    
    print(f"Enrollment API response: {json.dumps(enroll_res, indent=2)}")

    # Run the roadmap generation task synchronously in UAT/test mode
    print(f"Executing generate_personalized_roadmap synchronously for: {enroll_res['enrollment']}")
    from job_search_ai.tasks import generate_personalized_roadmap
    generate_personalized_roadmap(enrollment_name=enroll_res["enrollment"])
    
    # Step 5: Verify the created active plan and print active dashboard data
    print("\n[Step 5] Fetching active plan details for student dashboard...")
    import time
    
    active_plan = None
    max_wait = 90
    wait_interval = 5
    elapsed = 0
    
    while elapsed < max_wait:
        active_plan = get_active_plan(student_email)
        if active_plan.get("has_active_plan"):
            print(f"Active plan found after {elapsed} seconds!")
            break
        print(f"Waiting for roadmap generation... ({elapsed}s elapsed)")
        time.sleep(wait_interval)
        elapsed += wait_interval
        
    print("\n================ ACTIVE JOURNEY DASHBOARD DATA ================")
    print(json.dumps(active_plan, indent=2))
    print("===============================================================")
    
    # Verify that the dummy enrollment was paused
    dummy_status = frappe.db.get_value("Student Path Enrollment", dummy_enrollment.name, "status")
    print(f"\n[Auto-Pause Verification] Dummy enrollment status is now: {dummy_status}")
    assert dummy_status == "Paused", f"Expected dummy enrollment status to be Paused, but got {dummy_status}!"
    print("[Auto-Pause Verification] Success! The active path enrollment was successfully auto-paused!")

    # Check that new attributes are present in the active plan
    assert active_plan.get("has_active_plan") is True, "Active plan flag is missing or False!"
    assert "difficulty_level" in active_plan, "difficulty_level attribute is missing!"
    assert "average_salary" in active_plan, "average_salary attribute is missing!"
    assert "prerequisite_skills" in active_plan, "prerequisite_skills attribute is missing!"
    assert "missing_skills" in active_plan, "missing_skills attribute is missing!"
    assert len(active_plan.get("milestones", [])) > 0, "No milestones were generated!"
    
    print("\n=== FLOW TEST COMPLETED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_test()
