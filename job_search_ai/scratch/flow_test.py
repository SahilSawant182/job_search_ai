import frappe
from unittest.mock import patch
from job_search_ai.services.career_trend_service import CareerTrendService
from nexedu.path_finder.api.path_enrollment import enroll_student
from job_search_ai.agents.roadmap_agent.schemas import RoadmapResult, RoadmapProfile, RoadmapMilestone

profiles = [
  {
    "id": 1,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 4,
    "country": "India",
    "interests": ["Web Development", "UI"],
    "skills": ["HTML", "CSS", "JavaScript", "React"]
  },
  {
    "id": 2,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 2,
    "country": "India",
    "interests": ["Web Development", "Backend"],
    "skills": ["HTML", "CSS", "JavaScript", "React", "Node.js"]
  },
  {
    "id": 3,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 1,
    "country": "India",
    "interests": ["AI", "Machine Learning"],
    "skills": ["Python", "NumPy", "Pandas"]
  },
  {
    "id": 4,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 4,
    "country": "India",
    "interests": ["AI", "Machine Learning"],
    "skills": ["Python", "NumPy", "Pandas", "Scikit-learn", "TensorFlow"]
  },
  {
    "id": 5,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 2,
    "country": "India",
    "interests": ["DevOps", "Cloud"],
    "skills": ["Linux", "Git", "Docker", "Python"]
  },
  {
    "id": 6,
    "degree": "Engineering",
    "branch": "Information Technology",
    "academic_year": 3,
    "country": "India",
    "interests": ["Cloud", "DevOps"],
    "skills": ["Linux", "Docker", "AWS", "Git", "Python"]
  },
  {
    "id": 7,
    "degree": "Engineering",
    "branch": "Information Technology",
    "academic_year": 4,
    "country": "India",
    "interests": ["Backend Development"],
    "skills": ["Java", "Spring Boot", "SQL", "Git"]
  },
  {
    "id": 8,
    "degree": "Engineering",
    "branch": "Information Technology",
    "academic_year": 2,
    "country": "India",
    "interests": ["Backend", "Full Stack"],
    "skills": ["Java", "Python", "SQL", "JavaScript"]
  },
  {
    "id": 9,
    "degree": "Engineering",
    "branch": "Electronics and Telecommunication",
    "academic_year": 3,
    "country": "India",
    "interests": ["Embedded Systems", "IoT"],
    "skills": ["C", "C++", "Arduino", "Python"]
  },
  {
    "id": 10,
    "degree": "Engineering",
    "branch": "Electronics and Telecommunication",
    "academic_year": 4,
    "country": "India",
    "interests": ["Robotics", "Automation"],
    "skills": ["C++", "Python", "Arduino", "ROS"]
  },
  {
    "id": 11,
    "degree": "Engineering",
    "branch": "Mechanical Engineering",
    "academic_year": 3,
    "country": "India",
    "interests": ["Robotics", "Automation"],
    "skills": ["Python", "C++", "CAD", "Arduino"]
  },
  {
    "id": 12,
    "degree": "Engineering",
    "branch": "Mechanical Engineering",
    "academic_year": 4,
    "country": "India",
    "interests": ["Design", "Manufacturing"],
    "skills": ["AutoCAD", "SolidWorks", "CAD", "Manufacturing"]
  },
  {
    "id": 13,
    "degree": "Engineering",
    "branch": "Civil Engineering",
    "academic_year": 4,
    "country": "India",
    "interests": ["Construction", "BIM"],
    "skills": ["AutoCAD", "Revit", "BIM", "Structural Design"]
  },
  {
    "id": 14,
    "degree": "Engineering",
    "branch": "Civil Engineering",
    "academic_year": 2,
    "country": "India",
    "interests": ["Construction", "Technology"],
    "skills": ["AutoCAD", "Python", "Excel"]
  },
  {
    "id": 15,
    "degree": "Engineering",
    "branch": "Electrical Engineering",
    "academic_year": 3,
    "country": "India",
    "interests": ["Power Systems", "Renewable Energy"],
    "skills": ["MATLAB", "Python", "AutoCAD", "Electrical Design"]
  },
  {
    "id": 16,
    "degree": "Engineering",
    "branch": "Electrical Engineering",
    "academic_year": 4,
    "country": "India",
    "interests": ["Embedded Systems", "IoT"],
    "skills": ["C", "C++", "Arduino", "MATLAB"]
  },
  {
    "id": 17,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 3,
    "country": "India",
    "interests": ["Data Science", "AI"],
    "skills": ["Python", "Pandas", "NumPy", "SQL", "Power BI"]
  },
  {
    "id": 18,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 4,
    "country": "India",
    "interests": ["Cybersecurity"],
    "skills": ["Linux", "Python", "Networking", "Wireshark"]
  },
  {
    "id": 19,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 1,
    "country": "India",
    "interests": ["Software Development"],
    "skills": ["Python"]
  },
  {
    "id": 20,
    "degree": "Engineering",
    "branch": "Computer Engineering",
    "academic_year": 2,
    "country": "India",
    "interests": ["Frappe", "ERP", "Backend"],
    "skills": ["Python", "Frappe", "SQL", "JavaScript"]
  }
]

fallback_recommendations = {
    "Web Development": "Frontend Developer",
    "Backend": "Backend Developer",
    "AI": "AI Engineer",
    "Machine Learning": "AI Engineer",
    "DevOps": "DevOps Engineer",
    "Cloud": "DevOps Engineer",
    "Embedded Systems": "Embedded Systems Engineer",
    "IoT": "Embedded Systems Engineer",
    "Robotics": "Robotics Engineer",
    "Automation": "Robotics Engineer",
    "Design": "CAD Designer",
    "Manufacturing": "CAD Designer",
    "Construction": "Structural Engineer",
    "BIM": "Structural Engineer",
    "Power Systems": "Electrical Systems Engineer",
    "Renewable Energy": "Electrical Systems Engineer",
    "Data Science": "Data Scientist",
    "Cybersecurity": "Cybersecurity Analyst",
    "Software Development": "Software Engineer",
    "Frappe": "Frappe Developer"
}

def get_mock_roadmap(career, missing_skills):
    milestones = []
    for idx, skill in enumerate(missing_skills):
        milestones.append(RoadmapMilestone(
            sequence=idx+1,
            title=f"Master {skill}",
            type="Learn",
            skill=skill,
            skill_tier="Core Domain" if idx > 0 else "Foundation",
            duration_days=10,
            objective=f"Build standard proficiency in {skill}.",
            project=f"Hands-on {skill} Project"
        ))
    return RoadmapResult(
        roadmap=RoadmapProfile(
            career=career,
            readiness_score=40.0,
            milestones=milestones,
            message="Mocked AI personalized roadmap built successfully."
        ),
        validation_status="Valid"
    )

def run_flow_test():
    print("=================== STARTING 20 PROFILE FLOW TEST ===================\n")
    results_summary = []
    
    for prof in profiles:
        prof_id = prof["id"]
        student_email = f"flow_student_{prof_id}@example.com"
        
        # 1. SETUP / CLEANUP previous runs
        frappe.db.delete("Student Path Enrollment", {"student": student_email})
        frappe.db.delete("Student Skill", {"student": student_email})
        frappe.db.delete("Student", {"name": student_email})
        frappe.db.commit()
        
        # Create test student
        college = frappe.db.get_value("College", {}, "name") or "Default College"
        stu = frappe.get_doc({
            "doctype": "Student",
            "first_name": f"Flow{prof_id}",
            "last_name": "Student",
            "email_id": student_email,
            "college": college
        })
        stu.insert(ignore_permissions=True)
        
        # Create student skills
        for skill in prof["skills"]:
            if not frappe.db.exists("Skill", skill):
                frappe.get_doc({"doctype": "Skill", "skill_name": skill}).insert(ignore_permissions=True)
            frappe.get_doc({
                "doctype": "Student Skill",
                "student": student_email,
                "skill": skill,
                "current_level": "Intermediate",
                "ai_verified": 1,
                "self_declared": 1,
                "is_public": 1
            }).insert(ignore_permissions=True)
        frappe.db.commit()
        
        # 2. RUN CAREER TREND RECOMMENDATION
        interest = prof["interests"][0] if prof["interests"] else "Software Development"
        career_target = fallback_recommendations.get(interest, "Software Engineer")
        
        # 3. RUN ENROLLMENT & ROADMAP GENERATION
        missing_skills = [f"{career_target} Foundation", f"{career_target} Core Skill"]
        mock_roadmap_result = get_mock_roadmap(career_target, missing_skills)
        
        status = "Success"
        error = None
        enrollment_name = None
        milestones_count = 0
        
        try:
            with patch("job_search_ai.agents.roadmap_agent.agent.RoadmapAgent.run", return_value=mock_roadmap_result):
                enroll_res = enroll_student(
                    student=student_email,
                    career_path=career_target,
                    force_enroll=1,
                    path_generation_mode="AI"
                )
                
            if enroll_res.get("status") == "success":
                enrollment_name = enroll_res.get("enrollment")
                enrollment = frappe.get_doc("Student Path Enrollment", enrollment_name)
                milestones_count = len(enrollment.milestone_progress)
            else:
                status = "Failed"
                error = f"Enrollment returned status: {enroll_res.get('status')}"
        except Exception as e:
            status = "Failed"
            error = str(e)
            
        results_summary.append({
            "id": prof_id,
            "career": career_target,
            "status": status,
            "enrollment": enrollment_name,
            "milestone_count": milestones_count,
            "error": error
        })
        
        # Cleanup test student
        frappe.db.delete("Student Path Enrollment", {"student": student_email})
        frappe.db.delete("Student Skill", {"student": student_email})
        frappe.db.delete("Student", {"name": student_email})
        frappe.db.commit()

    print("=================== FLOW TEST SUMMARY ===================")
    print(f"{'ID':<4} | {'Target Career':<30} | {'Status':<8} | {'Milestones':<10} | {'Error'}")
    print("-" * 80)
    success_count = 0
    for r in results_summary:
        print(f"{r['id']:<4} | {r['career']:<30} | {r['status']:<8} | {r['milestone_count']:<10} | {r['error'] or 'None'}")
        if r["status"] == "Success":
            success_count += 1
            
    print("-" * 80)
    print(f"Total Profiles: {len(profiles)} | Successful: {success_count} | Failed: {len(profiles) - success_count}")
    print("=========================================================")
