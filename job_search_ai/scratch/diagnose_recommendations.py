# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import hashlib
import numpy as np
import frappe
from unittest.mock import patch
from groq import Groq

# Ensure Frappe workspace environment is imported
sys.path.append("/home/dev/frappe-bench/apps/job_search_ai")

from job_search_ai.agents.career_trend.agent import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile

STUDENT_PROFILES_JSON = """[
  {
    "profile_id": "STU001",
    "name": "Aarav Frontend Beginner",
    "degree": "B.Tech",
    "branch": "Computer Science",
    "year": 2,
    "country": "India",
    "interests": [
      "Frontend Development",
      "Web Development",
      "UI Development"
    ],
    "skills": [
      "HTML",
      "CSS",
      "JavaScript"
    ],
    "goal": "Frontend Developer",
    "experience_level": "Beginner",
    "expected_career_families": [
      "Frontend Developer",
      "Frontend Engineer",
      "UI Developer",
      "Web Developer",
      "React Developer"
    ]
  },
  {
    "profile_id": "STU002",
    "name": "Riya Frontend Advanced",
    "degree": "B.Tech",
    "branch": "Information Technology",
    "year": 4,
    "country": "India",
    "interests": [
      "Frontend Development",
      "React",
      "UI Engineering"
    ],
    "skills": [
      "HTML",
      "CSS",
      "JavaScript",
      "React",
      "Redux",
      "TypeScript",
      "Git"
    ],
    "goal": "Frontend Developer",
    "experience_level": "Advanced",
    "expected_career_families": [
      "Frontend Developer",
      "Frontend Engineer",
      "React Developer",
      "UI Engineer",
      "Web Developer"
    ]
  },
  {
    "profile_id": "STU003",
    "name": "Aditya Backend",
    "degree": "B.Tech",
    "branch": "Computer Science",
    "year": 3,
    "country": "India",
    "interests": [
      "Backend Development",
      "APIs",
      "Cloud Applications"
    ],
    "skills": [
      "Python",
      "SQL",
      "Git",
      "FastAPI",
      "PostgreSQL"
    ],
    "goal": "Backend Developer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Backend Developer",
      "Backend Engineer",
      "API Developer",
      "Server-Side Developer",
      "Python Developer"
    ]
  },
  {
    "profile_id": "STU004",
    "name": "Vihan Full Stack",
    "degree": "B.Tech",
    "branch": "Computer Science",
    "year": 3,
    "country": "India",
    "interests": [
      "Full Stack Development",
      "Web Applications",
      "SaaS"
    ],
    "skills": [
      "HTML",
      "CSS",
      "JavaScript",
      "React",
      "Node.js",
      "Express",
      "MongoDB",
      "Git"
    ],
    "goal": "Full Stack Developer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Full Stack Developer",
      "Full Stack Engineer",
      "Web Developer",
      "MERN Developer"
    ]
  },
  {
    "profile_id": "STU005",
    "name": "Yash AI Engineer",
    "degree": "B.Tech",
    "branch": "Artificial Intelligence and Data Science",
    "year": 4,
    "country": "India",
    "interests": [
      "Artificial Intelligence",
      "Deep Learning",
      "Generative AI"
    ],
    "skills": [
      "Python",
      "Machine Learning",
      "Deep Learning",
      "TensorFlow",
      "PyTorch",
      "Git"
    ],
    "goal": "AI Engineer",
    "experience_level": "Advanced",
    "expected_career_families": [
      "AI Engineer",
      "ML Engineer",
      "Machine Learning Engineer",
      "Deep Learning Engineer",
      "AI Developer"
    ]
  },
  {
    "profile_id": "STU006",
    "name": "Rahul Data Scientist",
    "degree": "B.Sc",
    "branch": "Statistics",
    "year": 3,
    "country": "India",
    "interests": [
      "Data Science",
      "Statistics",
      "Predictive Analytics"
    ],
    "skills": [
      "Python",
      "SQL",
      "Statistics",
      "Pandas",
      "Scikit-Learn",
      "Machine Learning"
    ],
    "goal": "Data Scientist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Data Scientist",
      "ML Engineer",
      "Data Analyst",
      "Analytics Engineer",
      "Statistician"
    ]
  },
  {
    "profile_id": "STU007",
    "name": "Karan DevOps",
    "degree": "B.Tech",
    "branch": "Information Technology",
    "year": 4,
    "country": "India",
    "interests": [
      "DevOps",
      "Cloud Engineering",
      "Infrastructure Automation"
    ],
    "skills": [
      "Git",
      "Linux",
      "Docker",
      "Kubernetes",
      "Terraform",
      "AWS",
      "Ansible",
      "Prometheus"
    ],
    "goal": "DevOps Engineer",
    "experience_level": "Advanced",
    "expected_career_families": [
      "DevOps Engineer",
      "Cloud Engineer",
      "Site Reliability Engineer",
      "SRE",
      "Platform Engineer"
    ]
  },
  {
    "profile_id": "STU008",
    "name": "Meera Frappe Developer",
    "degree": "B.Tech",
    "branch": "Computer Science",
    "year": 3,
    "country": "India",
    "interests": [
      "Frappe Framework",
      "ERPNext",
      "Enterprise Applications"
    ],
    "skills": [
      "Python",
      "Git",
      "SQL",
      "Frappe Framework",
      "Frappe ORM",
      "MariaDB",
      "Redis"
    ],
    "goal": "Frappe Developer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Frappe Developer",
      "ERPNext Developer",
      "Enterprise Applications Developer",
      "Python Developer",
      "Full Stack Developer",
      "Web Developer"
    ]
  },
  {
    "profile_id": "STU009",
    "name": "Arjun Cybersecurity",
    "degree": "B.Tech",
    "branch": "Cyber Security",
    "year": 3,
    "country": "India",
    "interests": [
      "Cybersecurity",
      "Ethical Hacking",
      "Network Security"
    ],
    "skills": [
      "Linux",
      "Networking",
      "Python",
      "Wireshark",
      "Nmap",
      "Git"
    ],
    "goal": "Cybersecurity Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Cybersecurity Analyst",
      "Security Engineer",
      "Information Security Analyst",
      "Security Analyst",
      "Penetration Tester",
      "Cybersecurity Specialist",
      "Security Manager"
    ]
  },
  {
    "profile_id": "STU010",
    "name": "Sneha Cloud Engineer",
    "degree": "B.Tech",
    "branch": "Computer Science",
    "year": 4,
    "country": "India",
    "interests": [
      "Cloud Computing",
      "Cloud Architecture",
      "Infrastructure"
    ],
    "skills": [
      "AWS",
      "Linux",
      "Docker",
      "Terraform",
      "Networking",
      "Python"
    ],
    "goal": "Cloud Engineer",
    "experience_level": "Advanced",
    "expected_career_families": [
      "Cloud Architect",
      "Cloud Engineer",
      "Solutions Architect",
      "AWS Architect",
      "Cloud Developer"
    ]
  },
  {
    "profile_id": "STU011",
    "name": "Rohan Mechanical Robotics",
    "degree": "B.E.",
    "branch": "Mechanical Engineering",
    "year": 3,
    "country": "India",
    "interests": [
      "Robotics",
      "Automation",
      "Manufacturing"
    ],
    "skills": [
      "CAD",
      "MATLAB",
      "Python",
      "PLC Basics"
    ],
    "goal": "Robotics Engineer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Robotics Engineer",
      "Automation Engineer",
      "Controls Engineer",
      "Manufacturing Automation Engineer",
      "Mechatronics Engineer"
    ]
  },
  {
    "profile_id": "STU012",
    "name": "Isha Mechanical Design",
    "degree": "B.E.",
    "branch": "Mechanical Engineering",
    "year": 4,
    "country": "India",
    "interests": [
      "Product Design",
      "Mechanical Design",
      "Manufacturing"
    ],
    "skills": [
      "AutoCAD",
      "SolidWorks",
      "CAD",
      "GD&T"
    ],
    "goal": "Mechanical Design Engineer",
    "experience_level": "Advanced",
    "expected_career_families": [
      "Product Designer",
      "Product Engineer",
      "Mechanical Engineer",
      "CAD Engineer",
      "Mechanical Design Engineer",
      "Product Design Engineer",
      "Structural Engineer"
    ]
  },
  {
    "profile_id": "STU013",
    "name": "Om Electrical Engineer",
    "degree": "B.E.",
    "branch": "Electrical Engineering",
    "year": 3,
    "country": "India",
    "interests": [
      "Power Systems",
      "Electrical Design",
      "Renewable Energy"
    ],
    "skills": [
      "MATLAB",
      "Circuit Analysis",
      "AutoCAD Electrical",
      "Electrical Machines"
    ],
    "goal": "Electrical Engineer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Electrical Engineer",
      "Power Systems Engineer",
      "Electrical Design Engineer",
      "Power System Engineer"
    ]
  },
  {
    "profile_id": "STU014",
    "name": "Ananya Electronics Embedded",
    "degree": "B.E.",
    "branch": "Electronics and Telecommunication",
    "year": 3,
    "country": "India",
    "interests": [
      "Embedded Systems",
      "IoT",
      "Electronics"
    ],
    "skills": [
      "C",
      "C++",
      "Microcontrollers",
      "Arduino",
      "Embedded C"
    ],
    "goal": "Embedded Systems Engineer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Embedded Systems Engineer",
      "IoT Developer",
      "Firmware Engineer",
      "Hardware Engineer",
      "Electronics Engineer",
      "VLSI Engineer"
    ]
  },
  {
    "profile_id": "STU015",
    "name": "Vivek Civil Engineer",
    "degree": "B.E.",
    "branch": "Civil Engineering",
    "year": 4,
    "country": "India",
    "interests": [
      "Construction",
      "Infrastructure",
      "Structural Engineering"
    ],
    "skills": [
      "AutoCAD",
      "STAAD Pro",
      "Structural Analysis",
      "Project Planning"
    ],
    "goal": "Civil Engineer",
    "experience_level": "Advanced",
    "expected_career_families": [
      "Civil Engineer",
      "Structural Engineer",
      "Infrastructure Engineer",
      "Construction Engineer",
      "Construction Manager",
      "Site Engineer"
    ]
  },
  {
    "profile_id": "STU016",
    "name": "Kavya Chemical",
    "degree": "B.E.",
    "branch": "Chemical Engineering",
    "year": 3,
    "country": "India",
    "interests": [
      "Process Engineering",
      "Manufacturing",
      "Energy"
    ],
    "skills": [
      "Process Simulation",
      "MATLAB",
      "Thermodynamics",
      "Process Control"
    ],
    "goal": "Process Engineer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Chemical Engineer",
      "Process Engineer",
      "Petrochemical Engineer",
      "Refinery Engineer"
    ]
  },
  {
    "profile_id": "STU017",
    "name": "Tanya Statistics",
    "degree": "B.Sc",
    "branch": "Statistics",
    "year": 2,
    "country": "India",
    "interests": [
      "Statistics",
      "Data Analysis",
      "Research"
    ],
    "skills": [
      "Excel",
      "Statistics",
      "R",
      "SQL"
    ],
    "goal": "Data Analyst",
    "experience_level": "Beginner",
    "expected_career_families": [
      "Data Analyst",
      "Statistical Analyst",
      "Data Scientist",
      "Business Analyst",
      "Analytics Specialist"
    ]
  },
  {
    "profile_id": "STU018",
    "name": "Priya Mathematics",
    "degree": "B.Sc",
    "branch": "Mathematics",
    "year": 3,
    "country": "India",
    "interests": [
      "Analytics",
      "Statistics",
      "Machine Learning"
    ],
    "skills": [
      "Python",
      "Statistics",
      "Linear Algebra",
      "SQL"
    ],
    "goal": "Data Scientist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Data Scientist",
      "Quantitative Analyst",
      "Data Analyst",
      "ML Engineer",
      "Statistician"
    ]
  },
  {
    "profile_id": "STU019",
    "name": "Aditi Physics",
    "degree": "B.Sc",
    "branch": "Physics",
    "year": 3,
    "country": "India",
    "interests": [
      "Research",
      "Simulation",
      "Data Analysis"
    ],
    "skills": [
      "Python",
      "MATLAB",
      "Numerical Methods",
      "Statistics"
    ],
    "goal": "Research Scientist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Research Scientist",
      "Physicist",
      "Research Associate",
      "Research Analyst",
      "Lab Technician",
      "Biotech Researcher"
    ]
  },
  {
    "profile_id": "STU020",
    "name": "Nikhil Biotechnology",
    "degree": "B.Sc",
    "branch": "Biotechnology",
    "year": 3,
    "country": "India",
    "interests": [
      "Biotechnology",
      "Genomics",
      "Healthcare Research"
    ],
    "skills": [
      "Biology",
      "Biostatistics",
      "Python",
      "Laboratory Techniques"
    ],
    "goal": "Bioinformatics Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Bioinformatics Analyst",
      "Bioinformatics Engineer",
      "Bioinformatics Specialist",
      "Biotech Researcher",
      "Research Associate"
    ]
  },
  {
    "profile_id": "STU021",
    "name": "Sahil Finance",
    "degree": "B.Com",
    "branch": "Commerce",
    "year": 3,
    "country": "India",
    "interests": [
      "Finance",
      "Investment Analysis",
      "Banking"
    ],
    "skills": [
      "Excel",
      "Financial Modeling",
      "Accounting",
      "Financial Analysis"
    ],
    "goal": "Financial Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Financial Analyst",
      "Investment Analyst",
      "Finance Analyst",
      "Equity Analyst"
    ]
  },
  {
    "profile_id": "STU022",
    "name": "Neha Accounting",
    "degree": "B.Com",
    "branch": "Accounting and Finance",
    "year": 3,
    "country": "India",
    "interests": [
      "Accounting",
      "Auditing",
      "Taxation"
    ],
    "skills": [
      "Accounting",
      "Tally",
      "Excel",
      "GST"
    ],
    "goal": "Accountant",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Accountant",
      "Auditor",
      "Tax Consultant",
      "Financial Accountant",
      "CPA",
      "Auditing and Assurance Spec"
    ]
  },
  {
    "profile_id": "STU023",
    "name": "Riya Investment",
    "degree": "BBA",
    "branch": "Finance",
    "year": 3,
    "country": "India",
    "interests": [
      "Investment Banking",
      "Equity Research",
      "Capital Markets"
    ],
    "skills": [
      "Financial Modeling",
      "Excel",
      "Valuation",
      "Financial Analysis"
    ],
    "goal": "Investment Banking Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Investment Banking Analyst",
      "Financial Services Analyst",
      "Investment Advisor",
      "Finance Analyst"
    ]
  },
  {
    "profile_id": "STU024",
    "name": "Kunal Banking",
    "degree": "B.Com",
    "branch": "Commerce",
    "year": 2,
    "country": "India",
    "interests": [
      "Banking",
      "Financial Services",
      "Risk Management"
    ],
    "skills": [
      "Excel",
      "Accounting",
      "Financial Analysis",
      "Communication"
    ],
    "goal": "Banking Operations Analyst",
    "experience_level": "Beginner",
    "expected_career_families": [
      "Banking Analyst",
      "Financial Services Analyst",
      "Risk Analyst",
      "Credit Analyst"
    ]
  },
  {
    "profile_id": "STU025",
    "name": "Aman Marketing",
    "degree": "BBA",
    "branch": "Marketing",
    "year": 3,
    "country": "India",
    "interests": [
      "Digital Marketing",
      "Brand Strategy",
      "Advertising"
    ],
    "skills": [
      "SEO",
      "Google Analytics",
      "Content Writing",
      "Social Media Marketing"
    ],
    "goal": "Digital Marketing Specialist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Marketing Analyst",
      "Digital Marketing Specialist",
      "SEO Specialist",
      "Marketing Manager",
      "Brand Manager",
      "Digital Marketing Analyst"
    ]
  },
  {
    "profile_id": "STU026",
    "name": "Shreya HR",
    "degree": "BBA",
    "branch": "Human Resources",
    "year": 3,
    "country": "India",
    "interests": [
      "Human Resources",
      "Recruitment",
      "Employee Engagement"
    ],
    "skills": [
      "Communication",
      "Recruitment",
      "Excel",
      "Interviewing"
    ],
    "goal": "HR Specialist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "HR Manager",
      "Human Resources Manager",
      "Talent Acquisition Specialist",
      "HR Business Partner",
      "Employee Experience Manager",
      "Employee Engagement Specialist",
      "Talent Acquisition Specialist"
    ]
  },
  {
    "profile_id": "STU027",
    "name": "Dev Business Analyst",
    "degree": "BBA",
    "branch": "Business Analytics",
    "year": 3,
    "country": "India",
    "interests": [
      "Business Analytics",
      "Process Improvement",
      "Data Analysis"
    ],
    "skills": [
      "Excel",
      "SQL",
      "Power BI",
      "Requirements Gathering"
    ],
    "goal": "Business Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Business Analyst",
      "Management Consultant",
      "Strategy Analyst",
      "Business Strategy Manager"
    ]
  },
  {
    "profile_id": "STU028",
    "name": "Mahi Product Management",
    "degree": "BBA",
    "branch": "Business Administration",
    "year": 3,
    "country": "India",
    "interests": [
      "Product Management",
      "Technology Products",
      "Business Strategy"
    ],
    "skills": [
      "Market Research",
      "Product Strategy",
      "Excel",
      "Communication"
    ],
    "goal": "Product Manager",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Product Manager",
      "Product Owner",
      "Senior Product Manager",
      "Associate Product Manager",
      "Product Management Specialist",
      "Data-Driven Product Manager"
    ]
  },
  {
    "profile_id": "STU029",
    "name": "Varun Operations",
    "degree": "BBA",
    "branch": "Operations Management",
    "year": 3,
    "country": "India",
    "interests": [
      "Operations",
      "Supply Chain",
      "Process Optimization"
    ],
    "skills": [
      "Excel",
      "Supply Chain Basics",
      "Process Mapping",
      "Data Analysis"
    ],
    "goal": "Operations Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Operations Manager",
      "Operations Analyst",
      "Supply Chain Manager",
      "Business Operations Manager",
      "Process Manager"
    ]
  },
  {
    "profile_id": "STU030",
    "name": "Pooja Entrepreneurship",
    "degree": "BBA",
    "branch": "Entrepreneurship",
    "year": 4,
    "country": "India",
    "interests": [
      "Entrepreneurship",
      "Startups",
      "Business Strategy"
    ],
    "skills": [
      "Business Planning",
      "Market Research",
      "Communication",
      "Financial Modeling"
    ],
    "goal": "Entrepreneur",
    "experience_level": "Advanced",
    "expected_career_families": [
      "Entrepreneur",
      "Business Development Manager",
      "Startup Founder",
      "Business Developer",
      "Venture Analyst"
    ]
  },
  {
    "profile_id": "STU031",
    "name": "Aarya UI UX Designer",
    "degree": "B.Des",
    "branch": "Communication Design",
    "year": 3,
    "country": "India",
    "interests": [
      "UI/UX Design",
      "Product Design",
      "User Research"
    ],
    "skills": [
      "Figma",
      "Wireframing",
      "Prototyping",
      "User Research"
    ],
    "goal": "UI UX Designer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "UX Designer",
      "UI Designer",
      "UX/UI Designer",
      "Product Designer",
      "Interaction Designer",
      "UI/UX Designer"
    ]
  },
  {
    "profile_id": "STU032",
    "name": "Rohit Graphic Designer",
    "degree": "B.Des",
    "branch": "Graphic Design",
    "year": 3,
    "country": "India",
    "interests": [
      "Graphic Design",
      "Branding",
      "Visual Communication"
    ],
    "skills": [
      "Photoshop",
      "Illustrator",
      "Typography",
      "Brand Design"
    ],
    "goal": "Graphic Designer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Graphic Designer",
      "Visual Designer",
      "Brand Designer",
      "Creative Designer"
    ]
  },
  {
    "profile_id": "STU033",
    "name": "Ira Animation Student",
    "degree": "B.Des",
    "branch": "Animation",
    "year": 3,
    "country": "India",
    "interests": [
      "Animation",
      "3D Design",
      "Motion Graphics"
    ],
    "skills": [
      "Blender",
      "3D Modeling",
      "Animation",
      "After Effects"
    ],
    "goal": "3D Artist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "3D Animator",
      "Animation Director",
      "3D Artist",
      "Motion Graphics Designer",
      "VFX Artist"
    ]
  },
  {
    "profile_id": "STU034",
    "name": "Kabir Content Creator",
    "degree": "BA",
    "branch": "Mass Communication",
    "year": 3,
    "country": "India",
    "interests": [
      "Content Creation",
      "Social Media",
      "Video Production"
    ],
    "skills": [
      "Video Editing",
      "Content Writing",
      "Storytelling",
      "Social Media"
    ],
    "goal": "Content Creator",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Content Creator",
      "Content Writer",
      "Social Media Manager",
      "Digital Content Specialist",
      "Video Content Creator",
      "Content Creation Specialist"
    ]
  },
  {
    "profile_id": "STU035",
    "name": "Anjali Psychology",
    "degree": "BA",
    "branch": "Psychology",
    "year": 3,
    "country": "India",
    "interests": [
      "Psychology",
      "Mental Wellbeing",
      "Counselling"
    ],
    "skills": [
      "Communication",
      "Psychological Assessment",
      "Counselling Basics",
      "Research"
    ],
    "goal": "Counsellor",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Counsellor",
      "Psychologist",
      "Mental Health Counsellor",
      "Therapist",
      "I-O Psychology Consultant",
      "Clinical Psychologist",
      "School Psychologist"
    ]
  },
  {
    "profile_id": "STU036",
    "name": "Sameer Sociology",
    "degree": "BA",
    "branch": "Sociology",
    "year": 3,
    "country": "India",
    "interests": [
      "Social Research",
      "Community Development",
      "Public Policy"
    ],
    "skills": [
      "Research",
      "Data Collection",
      "Communication",
      "Report Writing"
    ],
    "goal": "Social Researcher",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Social Researcher",
      "Social Scientist",
      "Sociologist",
      "Research Analyst",
      "Policy Researcher"
    ]
  },
  {
    "profile_id": "STU037",
    "name": "Megha Political Science",
    "degree": "BA",
    "branch": "Political Science",
    "year": 3,
    "country": "India",
    "interests": [
      "Public Policy",
      "Governance",
      "Politics"
    ],
    "skills": [
      "Research",
      "Policy Analysis",
      "Writing",
      "Public Speaking"
    ],
    "goal": "Policy Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Policy Analyst",
      "Public Policy Specialist",
      "Government Relations Analyst",
      "Political Analyst"
    ]
  },
  {
    "profile_id": "STU038",
    "name": "Sakshi English",
    "degree": "BA",
    "branch": "English Literature",
    "year": 2,
    "country": "India",
    "interests": [
      "Writing",
      "Publishing",
      "Content"
    ],
    "skills": [
      "Writing",
      "Editing",
      "Research",
      "Communication"
    ],
    "goal": "Content Writer",
    "experience_level": "Beginner",
    "expected_career_families": [
      "Content Writer",
      "Copywriter",
      "Editor",
      "Technical Writer",
      "Journalist",
      "Digital Content Writer"
    ]
  },
  {
    "profile_id": "STU039",
    "name": "Rahul Law",
    "degree": "LLB",
    "branch": "Law",
    "year": 3,
    "country": "India",
    "interests": [
      "Corporate Law",
      "Legal Research",
      "Compliance"
    ],
    "skills": [
      "Legal Research",
      "Contract Drafting",
      "Communication",
      "Compliance"
    ],
    "goal": "Corporate Lawyer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Corporate Lawyer",
      "Legal Analyst",
      "Corporate Law Specialist",
      "Compliance Analyst",
      "Legal Consultant"
    ]
  },
  {
    "profile_id": "STU040",
    "name": "Naina Legal Tech",
    "degree": "LLB",
    "branch": "Law",
    "year": 3,
    "country": "India",
    "interests": [
      "Legal Technology",
      "Cyber Law",
      "Technology Law"
    ],
    "skills": [
      "Legal Research",
      "Cyber Law",
      "Contract Drafting",
      "Basic Python"
    ],
    "goal": "Technology Lawyer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "LegalTech Specialist",
      "Legal Technology Consultant",
      "Legal Analyst",
      "Tech Law Specialist",
      "LegalTech Software Developer",
      "LegalTech Product Manager",
      "LawTech Consultant",
      "Legal Tech Specialist"
    ]
  },
  {
    "profile_id": "STU041",
    "name": "Diya Nursing",
    "degree": "B.Sc Nursing",
    "branch": "Nursing",
    "year": 3,
    "country": "India",
    "interests": [
      "Healthcare",
      "Patient Care",
      "Clinical Practice"
    ],
    "skills": [
      "Patient Care",
      "Clinical Assessment",
      "Communication",
      "Basic Medical Knowledge"
    ],
    "goal": "Registered Nurse",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Nurse",
      "Healthcare Administrator",
      "Clinical Nurse",
      "Patient Care Specialist"
    ]
  },
  {
    "profile_id": "STU042",
    "name": "Aarohi Pharmacy",
    "degree": "B.Pharm",
    "branch": "Pharmacy",
    "year": 3,
    "country": "India",
    "interests": [
      "Pharmaceuticals",
      "Drug Research",
      "Healthcare"
    ],
    "skills": [
      "Pharmacology",
      "Drug Formulation",
      "Laboratory Techniques",
      "Research"
    ],
    "goal": "Pharmacist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Pharma Marketing Specialist",
      "Pharmaceutical Data Analyst",
      "Regulatory Affairs Specialist",
      "Medical Sales",
      "Pharmaceutical Marketing Specialist"
    ]
  },
  {
    "profile_id": "STU043",
    "name": "Manav Medical",
    "degree": "MBBS",
    "branch": "Medicine",
    "year": 4,
    "country": "India",
    "interests": [
      "Medicine",
      "Clinical Care",
      "Healthcare"
    ],
    "skills": [
      "Clinical Diagnosis",
      "Patient Care",
      "Medical Research",
      "Communication"
    ],
    "goal": "Doctor",
    "experience_level": "Advanced",
    "expected_career_families": [
      "Healthcare Administrator",
      "Clinical Data Manager",
      "Hospital Administrator",
      "Medical Informatics Analyst"
    ]
  },
  {
    "profile_id": "STU044",
    "name": "Isha Biotechnology Healthcare",
    "degree": "B.Sc",
    "branch": "Biotechnology",
    "year": 3,
    "country": "India",
    "interests": [
      "Biotech",
      "Healthcare Technology",
      "Genomics"
    ],
    "skills": [
      "Biology",
      "PCR",
      "Biostatistics",
      "Research"
    ],
    "goal": "Biotechnology Researcher",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Biotech Research Scientist",
      "Biotech Data Analyst",
      "Genomics Analyst",
      "Biotechnology Manager",
      "Biotech Researcher"
    ]
  },
  {
    "profile_id": "STU045",
    "name": "Vikas Agriculture",
    "degree": "B.Sc",
    "branch": "Agriculture",
    "year": 3,
    "country": "India",
    "interests": [
      "Agriculture",
      "Agri Technology",
      "Sustainable Farming"
    ],
    "skills": [
      "Agronomy",
      "Crop Management",
      "Soil Science",
      "Data Collection"
    ],
    "goal": "Agronomist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Agriculture Specialist",
      "Agronomist",
      "Farm Management Specialist",
      "Agricultural Scientist"
    ]
  },
  {
    "profile_id": "STU046",
    "name": "Neel AgriTech",
    "degree": "B.Tech",
    "branch": "Agricultural Engineering",
    "year": 3,
    "country": "India",
    "interests": [
      "AgriTech",
      "IoT",
      "Smart Farming"
    ],
    "skills": [
      "Python",
      "IoT",
      "Sensors",
      "Data Analysis"
    ],
    "goal": "AgriTech Engineer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Agricultural Data Scientist",
      "AgriTech Specialist",
      "Precision Farming Engineer",
      "Smart Agriculture Consultant",
      "Agritech Specialist"
    ]
  },
  {
    "profile_id": "STU047",
    "name": "Tanvi Food Technology",
    "degree": "B.Tech",
    "branch": "Food Technology",
    "year": 3,
    "country": "India",
    "interests": [
      "Food Technology",
      "Food Safety",
      "Product Development"
    ],
    "skills": [
      "Food Chemistry",
      "Quality Control",
      "Food Processing",
      "Laboratory Techniques"
    ],
    "goal": "Food Technologist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Food Technologist",
      "Food Innovation Specialist",
      "Quality Control Specialist",
      "Food Scientist"
    ]
  },
  {
    "profile_id": "STU048",
    "name": "Rohan Hospitality",
    "degree": "BHM",
    "branch": "Hotel Management",
    "year": 3,
    "country": "India",
    "interests": [
      "Hospitality",
      "Hotels",
      "Travel"
    ],
    "skills": [
      "Customer Service",
      "Hotel Operations",
      "Communication",
      "Event Management"
    ],
    "goal": "Hotel Operations Manager",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Hotel Manager",
      "Hospitality Manager",
      "Customer Service Manager",
      "Travel and Tourism Manager"
    ]
  },
  {
    "profile_id": "STU049",
    "name": "Maya Tourism",
    "degree": "BBA",
    "branch": "Tourism Management",
    "year": 3,
    "country": "India",
    "interests": [
      "Travel",
      "Tourism",
      "Event Management"
    ],
    "skills": [
      "Travel Planning",
      "Customer Service",
      "Communication",
      "Event Management"
    ],
    "goal": "Travel Consultant",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Travel and Tourism Manager",
      "Tourism Consultant",
      "Destination Manager",
      "Travel Planner",
      "Travel and Tourism Consultant"
    ]
  },
  {
    "profile_id": "STU050",
    "name": "Raj Education",
    "degree": "B.Ed",
    "branch": "Education",
    "year": 2,
    "country": "India",
    "interests": [
      "Teaching",
      "Education",
      "Child Development"
    ],
    "skills": [
      "Lesson Planning",
      "Communication",
      "Classroom Management",
      "Assessment"
    ],
    "goal": "Teacher",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Teacher",
      "Educational Consultant",
      "Curriculum Developer",
      "School Administrator",
      "Middle School Teacher"
    ]
  },
  {
    "profile_id": "STU051",
    "name": "Nidhi Educational Technology",
    "degree": "B.Ed",
    "branch": "Education Technology",
    "year": 2,
    "country": "India",
    "interests": [
      "EdTech",
      "Online Learning",
      "Instructional Design"
    ],
    "skills": [
      "Instructional Design",
      "Content Development",
      "LMS",
      "Communication"
    ],
    "goal": "Instructional Designer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Instructional Designer",
      "EdTech Specialist",
      "Educational Technology Specialist",
      "eLearning Developer",
      "Online Learning Designer"
    ]
  },
  {
    "profile_id": "STU052",
    "name": "Aman Economics",
    "degree": "BA",
    "branch": "Economics",
    "year": 3,
    "country": "India",
    "interests": [
      "Economics",
      "Finance",
      "Market Research"
    ],
    "skills": [
      "Economics",
      "Statistics",
      "Excel",
      "Data Analysis"
    ],
    "goal": "Economic Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Market Research Analyst",
      "Financial Analyst",
      "Economic Analyst",
      "Research Economist",
      "Monetary Policy Specialist",
      "Economic Planner"
    ]
  },
  {
    "profile_id": "STU053",
    "name": "Pallavi Journalism",
    "degree": "BA",
    "branch": "Journalism",
    "year": 3,
    "country": "India",
    "interests": [
      "Journalism",
      "Media",
      "Investigative Reporting"
    ],
    "skills": [
      "Writing",
      "Research",
      "Interviewing",
      "Video Editing"
    ],
    "goal": "Journalist",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Journalist",
      "Broadcast Journalist",
      "Digital Media Specialist",
      "Content Journalist",
      "Data Journalist",
      "Digital Journalist",
      "Multilingual Journalist",
      "Digital Journalism Specialist"
    ]
  },
  {
    "profile_id": "STU054",
    "name": "Ayesha Fashion",
    "degree": "B.Des",
    "branch": "Fashion Design",
    "year": 3,
    "country": "India",
    "interests": [
      "Fashion Design",
      "Apparel",
      "Creative Design"
    ],
    "skills": [
      "Fashion Illustration",
      "Pattern Making",
      "Textile Knowledge",
      "Design"
    ],
    "goal": "Fashion Designer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Fashion Designer",
      "E-commerce Fashion Designer",
      "Digital Fashion Designer",
      "Retail Fashion Buyer"
    ]
  },
  {
    "profile_id": "STU055",
    "name": "Sameer Career Switcher",
    "degree": "B.Com",
    "branch": "Commerce",
    "year": 3,
    "country": "India",
    "interests": [
      "Software Development",
      "Web Development",
      "AI"
    ],
    "skills": [
      "Excel",
      "SQL",
      "HTML",
      "CSS",
      "Python"
    ],
    "goal": "Career Switch",
    "experience_level": "Beginner",
    "expected_career_families": [
      "Web Development Manager",
      "Engineering Manager",
      "Software Development Manager",
      "Tech Lead"
    ]
  },
  {
    "profile_id": "STU056",
    "name": "Pooja Business to Data",
    "degree": "BBA",
    "branch": "Business Analytics",
    "year": 3,
    "country": "India",
    "interests": [
      "Data Science",
      "Business Analytics",
      "Machine Learning"
    ],
    "skills": [
      "Excel",
      "SQL",
      "Power BI",
      "Python"
    ],
    "goal": "Data Analyst",
    "experience_level": "Beginner",
    "expected_career_families": [
      "Data Scientist",
      "Data Analyst",
      "Business Analyst",
      "Analytics Engineer",
      "Business/Data Analyst"
    ]
  },
  {
    "profile_id": "STU057",
    "name": "Ritesh Engineering to Finance",
    "degree": "B.Tech",
    "branch": "Mechanical Engineering",
    "year": 4,
    "country": "India",
    "interests": [
      "Finance",
      "Investment",
      "Analytics"
    ],
    "skills": [
      "Excel",
      "Python",
      "Statistics",
      "Financial Modeling"
    ],
    "goal": "Financial Analyst",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Financial Analyst",
      "Financial Planner",
      "Investment Analyst",
      "Quantitative Analyst",
      "Finance Analyst",
      "Workforce Analytics Special"
    ]
  },
  {
    "profile_id": "STU058",
    "name": "Snehal Creative Tech",
    "degree": "B.Des",
    "branch": "Interaction Design",
    "year": 3,
    "country": "India",
    "interests": [
      "UX Engineering",
      "Frontend Development",
      "Product Design"
    ],
    "skills": [
      "Figma",
      "HTML",
      "CSS",
      "JavaScript",
      "User Research"
    ],
    "goal": "UX Engineer",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Frontend Developer",
      "UX Designer",
      "UX Engineer",
      "UI Developer",
      "UX/UI Designer",
      "UX/UI Design Lead",
      "Design Systems Developer"
    ]
  },
  {
    "profile_id": "STU059",
    "name": "Harsh Mixed AI Business",
    "degree": "BBA",
    "branch": "Business Analytics",
    "year": 3,
    "country": "India",
    "interests": [
      "AI",
      "Business Strategy",
      "Product Management"
    ],
    "skills": [
      "Python",
      "SQL",
      "Excel",
      "Power BI",
      "Machine Learning"
    ],
    "goal": "AI Product Manager",
    "experience_level": "Intermediate",
    "expected_career_families": [
      "Business Analyst - AI",
      "AI Product Manager",
      "Data Scientist",
      "Product Manager",
      "Business Intelligence Analyst",
      "Data-Driven Product Manager",
      "AI Agent Developer"
    ]
  },
  {
    "profile_id": "STU060",
    "name": "Zero Skill Beginner",
    "degree": "B.A",
    "branch": "Arts",
    "year": 1,
    "country": "India",
    "interests": [
      "Technology",
      "Business",
      "Creative Work"
    ],
    "skills": [],
    "goal": "Explore Career",
    "experience_level": "Beginner",
    "expected_career_families": [
      "Career Explorer",
      "Junior Analyst",
      "Management Trainee",
      "AI Engineer",
      "Business Developer",
      "UI Designer",
      "UX Designer",
      "Software Developer"
    ]
  }
]"""

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    # Retrieve Groq API key
    api_key = frappe.conf.get("groq_api_key")
    if not api_key:
        raise RuntimeError("groq_api_key is not set in site_config.json")
    
    groq_client = Groq(api_key=api_key)

    def mock_execute_groq(*args, **kwargs):
        prompt = ""
        if args:
            for arg in args:
                if isinstance(arg, str):
                    prompt = arg
                    break
        if not prompt and "prompt" in kwargs:
            prompt = kwargs["prompt"]
        
        try:
            response = groq_client.chat.completions.create(
                model="groq/compound-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=30,
            )
            return response.choices[0].message.content or "{}"
        except Exception as exc:
            print(f"Mock Groq Execution Exception: {exc}")
            return "{}"

    def mock_embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode('utf-8')).digest()
        seed = int.from_bytes(h, 'big') % (2**32)
        rng = np.random.default_rng(seed)
        v = rng.uniform(-1.0, 1.0, 768)
        v /= np.linalg.norm(v)
        return v.tolist()

    # Start patches
    p_llm = patch("job_search_ai.agents.career_trend.llm_service.LLMService._call_llm", mock_execute_groq)
    p_kb = patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm", mock_execute_groq)
    p_ext = patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama", mock_execute_groq)
    p_ext_open = patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_openai_compat", mock_execute_groq)
    p_emb = patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed", mock_embed)

    p_llm.start()
    p_kb.start()
    p_ext.start()
    p_ext_open.start()
    p_emb.start()

    profiles_data = json.loads(STUDENT_PROFILES_JSON)
    agent = CareerTrendAgent()

    results = []

    print(f"Starting diagnosis for {len(profiles_data)} student profiles...")
    for idx, p in enumerate(profiles_data):
        pid = p["profile_id"]
        name = p["name"]
        
        # Build StudentProfile object (only passing fields it expects)
        student = StudentProfile(
            degree=p["degree"],
            branch=p["branch"],
            year=p["year"],
            country=p["country"],
            interests=p["interests"],
            skills=p["skills"]
        )

        print(f"[{idx+1}/{len(profiles_data)}] Processing {pid}: {name}...")

        # Run 1
        t0 = time.perf_counter()
        try:
            resp1 = agent.run(student)
            dur1 = time.perf_counter() - t0
            status1 = "SUCCESS"
            recs1 = [r.career for r in resp1.recommended_paths]
            metrics1 = getattr(resp1, "metrics", {})
            khit1 = metrics1.get("knowledge_hit", False)
            model1 = metrics1.get("model_name", "unknown")
            tavily1 = metrics1.get("tavily_used", False)
            llm_time1 = metrics1.get("llm_response_time", 0.0)
            search_time1 = metrics1.get("parallel_search_time", 0.0)
            kb_build_time1 = metrics1.get("kb_build_time", 0.0)
            err1 = None
        except Exception as exc:
            dur1 = time.perf_counter() - t0
            status1 = "FAIL"
            recs1 = []
            metrics1 = {}
            khit1 = False
            model1 = "N/A"
            tavily1 = False
            llm_time1 = 0.0
            search_time1 = 0.0
            kb_build_time1 = 0.0
            err1 = str(exc)

        # Small sleep to allow DB/API settling
        time.sleep(0.5)

        # Run 2
        t0 = time.perf_counter()
        try:
            resp2 = agent.run(student)
            dur2 = time.perf_counter() - t0
            status2 = "SUCCESS"
            recs2 = [r.career for r in resp2.recommended_paths]
            metrics2 = getattr(resp2, "metrics", {})
            khit2 = metrics2.get("knowledge_hit", False)
            model2 = metrics2.get("model_name", "unknown")
            tavily2 = metrics2.get("tavily_used", False)
            avg_sim2 = metrics2.get("avg_similarity_score", 0.0)
            comb_sim2 = metrics2.get("combined_similarity", 0.0)
            err2 = None
        except Exception as exc:
            dur2 = time.perf_counter() - t0
            status2 = "FAIL"
            recs2 = []
            metrics2 = {}
            khit2 = False
            model2 = "N/A"
            tavily2 = False
            avg_sim2 = 0.0
            comb_sim2 = 0.0
            err2 = str(exc)

        res = {
            "profile_id": pid,
            "name": name,
            "goal": p["goal"],
            "interests": p["interests"],
            "skills": p["skills"],
            
            "run1_status": status1,
            "run1_duration": dur1,
            "run1_recs": recs1,
            "run1_knowledge_hit": khit1,
            "run1_model": model1,
            "run1_tavily_used": tavily1,
            "run1_llm_time": llm_time1,
            "run1_search_time": search_time1,
            "run1_kb_build_time": kb_build_time1,
            "run1_error": err1,

            "run2_status": status2,
            "run2_duration": dur2,
            "run2_recs": recs2,
            "run2_knowledge_hit": khit2,
            "run2_model": model2,
            "run2_tavily_used": tavily2,
            "run2_avg_sim": avg_sim2,
            "run2_comb_sim": comb_sim2,
            "run2_error": err2
        }
        results.append(res)
        print(f"    Run 1: {dur1:.2f}s | Source={model1} | Hit={khit1} | Tavily={tavily1} | Recs={recs1}")
        print(f"    Run 2: {dur2:.2f}s | Source={model2} | Cache HIT={model2 == 'profile_recommendation_knowledge'} | Recs={recs2}")
        
        # Save intermediate results in case script is interrupted
        with open("/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch/intermediate_results.json", "w") as f:
            json.dump(results, f, indent=2)

    print("\nAll profiles processed. Writing final reports...")
    
    # Save final JSON results
    with open("/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch/final_results.json", "w") as f:
        json.dump(results, f, indent=2)
        
    print("Done.")

if __name__ == "__main__":
    run()
