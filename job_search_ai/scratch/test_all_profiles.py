# -*- coding: utf-8 -*-
"""
Comprehensive test script for 20 diverse student profiles (Science/Commerce/Arts/Agriculture).
Tests: CareerTrendAgent → SkillAgent → RoadmapAgent → Enrollment
Validates: tier correctness, CSE/non-CSE disambiguation, no ERP bias, skill quality.
"""

import frappe
import json
import time

PROFILES = [
    {"id": 21, "degree": "Science", "branch": "Physics", "year": 3, "country": "India", "interests": ["Data Science", "Research"], "skills": ["Python", "Statistics", "Excel"]},
    {"id": 22, "degree": "Science", "branch": "Chemistry", "year": 3, "country": "India", "interests": ["Research", "Pharmaceuticals"], "skills": ["Laboratory Analysis", "Chemistry", "Excel"]},
    {"id": 23, "degree": "Science", "branch": "Biotechnology", "year": 4, "country": "India", "interests": ["Biotechnology", "Research"], "skills": ["Biology", "Laboratory Techniques", "Bioinformatics"]},
    {"id": 24, "degree": "Science", "branch": "Mathematics", "year": 3, "country": "India", "interests": ["Data Science", "Analytics"], "skills": ["Statistics", "Mathematics", "Excel", "Python"]},
    {"id": 25, "degree": "Science", "branch": "Physics", "year": 4, "country": "India", "interests": ["Finance", "Analytics"], "skills": ["Mathematics", "Statistics", "Excel", "Financial Modeling"]},
    {"id": 26, "degree": "Commerce", "branch": "Accounting", "year": 4, "country": "India", "interests": ["Finance", "Accounting"], "skills": ["Accounting", "Tally", "Excel", "Financial Analysis"]},
    {"id": 27, "degree": "Commerce", "branch": "Finance", "year": 3, "country": "India", "interests": ["Investment", "Financial Analysis"], "skills": ["Excel", "Financial Modeling", "Accounting", "Statistics"]},
    {"id": 28, "degree": "Commerce", "branch": "Marketing", "year": 3, "country": "India", "interests": ["Digital Marketing", "Content"], "skills": ["SEO", "Content Writing", "Social Media Marketing", "Canva"]},
    {"id": 29, "degree": "Commerce", "branch": "Business Administration", "year": 4, "country": "India", "interests": ["Business Analytics", "Management"], "skills": ["Excel", "Power BI", "Business Analysis", "Presentation"]},
    {"id": 30, "degree": "Commerce", "branch": "Accounting", "year": 2, "country": "India", "interests": ["Business", "Entrepreneurship"], "skills": ["Accounting", "Excel", "Business Communication"]},
    {"id": 31, "degree": "Arts", "branch": "Psychology", "year": 3, "country": "India", "interests": ["Human Resources", "Psychology"], "skills": ["Communication", "Research", "Psychology", "Interviewing"]},
    {"id": 32, "degree": "Arts", "branch": "English", "year": 3, "country": "India", "interests": ["Content Writing", "Media"], "skills": ["Writing", "Editing", "Communication", "Research"]},
    {"id": 33, "degree": "Arts", "branch": "Economics", "year": 4, "country": "India", "interests": ["Data Analysis", "Finance"], "skills": ["Economics", "Statistics", "Excel", "Research"]},
    {"id": 34, "degree": "Arts", "branch": "Psychology", "year": 4, "country": "India", "interests": ["Counselling", "Human Resources"], "skills": ["Psychology", "Communication", "Counselling", "Research"]},
    {"id": 35, "degree": "Business Administration", "branch": "Marketing", "year": 4, "country": "India", "interests": ["Marketing", "Brand Management"], "skills": ["Digital Marketing", "SEO", "Market Research", "Communication"]},
    {"id": 36, "degree": "Business Administration", "branch": "Human Resources", "year": 3, "country": "India", "interests": ["Human Resources", "People Management"], "skills": ["Communication", "Recruitment", "Interviewing", "Excel"]},
    {"id": 37, "degree": "Agriculture", "branch": "Agricultural Science", "year": 4, "country": "India", "interests": ["Agriculture", "Agribusiness"], "skills": ["Agronomy", "Crop Management", "Agribusiness", "Excel"]},
    {"id": 38, "degree": "Agriculture", "branch": "Agricultural Engineering", "year": 3, "country": "India", "interests": ["Agri Technology", "Automation"], "skills": ["Agriculture", "IoT", "Data Analysis", "Excel"]},
    {"id": 39, "degree": "Science", "branch": "Biology", "year": 2, "country": "India", "interests": ["Healthcare", "Research"], "skills": ["Biology", "Laboratory Techniques", "Research"]},
    {"id": 40, "degree": "Commerce", "branch": "Finance", "year": 4, "country": "India", "interests": ["Data Analytics", "Finance"], "skills": ["Excel", "SQL", "Power BI", "Financial Analysis"]},
]

CSE_KEYWORDS = [
    "software", "developer", "web", "data scientist", "machine learning",
    "ai engineer", "devops", "cloud", "frontend", "backend", "full-stack",
    "fullstack", "cybersecurity", "blockchain", "data engineer"
]

# Use full-word markers to avoid false positives like "interpretation" containing "erp"
CSE_POLLUTION_MARKERS = [
    "frappe erp", "erpnext", "frappe framework",
    "erp integration", "erp automation", "erp workflow",
    "odoo erp", " erp "
]

FRAMEWORK_LEVEL_SKILLS = [
    "react", "node.js", "express.js", "django", "flask", "spring boot",
    "tensorflow", "pytorch", "mongodb", "postgresql", "kubernetes", "docker",
    "aws", "azure", "graphql"
]


def is_cse_role(role_name):
    rl = role_name.lower()
    return any(kw in rl for kw in CSE_KEYWORDS)


def validate_skill_profile(profile, role_name):
    issues = []
    warnings = []

    foundation = [s.lower() for s in (profile.foundation_skills or [])]
    core = [s.lower() for s in (profile.core_domain_skills or [])]
    industry = [s.lower() for s in (profile.industry_skills or [])]
    emerging = [s.lower() for s in (profile.emerging_skills or [])]
    all_skills = foundation + core + industry + emerging

    # ERP pollution
    for marker in CSE_POLLUTION_MARKERS:
        for sk in all_skills:
            if marker in sk:
                issues.append(f"ERP POLLUTION: '{sk}' found in {role_name}")

    # Min tier sizes
    if len(profile.foundation_skills) < 3:
        issues.append(f"SPARSE foundation: only {len(profile.foundation_skills)} skills ({profile.foundation_skills})")
    if len(profile.core_domain_skills) < 4:
        issues.append(f"SPARSE core_domain: only {len(profile.core_domain_skills)} skills ({profile.core_domain_skills})")
    if len(profile.emerging_skills) == 0:
        warnings.append("EMPTY emerging_skills — no future-trend skills added")

    # Cross-tier deduplication check
    seen = {}
    for tier_name, tier in [("foundation", foundation), ("core", core), ("industry", industry), ("emerging", emerging)]:
        for sk in tier:
            key = sk.strip().replace(" ", "").replace("-", "").replace("_", "")
            if key in seen:
                issues.append(f"DUPLICATE: '{sk}' in both {seen[key]} and {tier_name}")
            else:
                seen[key] = tier_name

    # CSE: frameworks must NOT be in foundation
    if is_cse_role(role_name):
        for fw in FRAMEWORK_LEVEL_SKILLS:
            if fw in foundation:
                warnings.append(f"MISPLACED: '{fw}' should NOT be in foundation tier for CSE role")

    # Non-CSE: no heavy CSE tools in foundation
    if not is_cse_role(role_name):
        cse_contam = [s for s in foundation if any(
            c in s for c in ["react", "node.js", "django", "flask", "kubernetes", "docker", "spring boot"]
        )]
        for s in cse_contam:
            issues.append(f"NON-CSE CONTAMINATION: '{s}' in foundation for non-CSE role '{role_name}'")

    return issues, warnings


def validate_milestones(milestones, career_path):
    issues = []
    warnings = []

    if not milestones:
        issues.append(f"NO MILESTONES generated for '{career_path}'")
        return issues, warnings

    for i, ms in enumerate(milestones):
        if not ms.get("milestone_title"):
            issues.append(f"Milestone {i+1}: missing milestone_title")
        if not ms.get("category"):
            issues.append(f"Milestone {i+1}: missing category")
        if not ms.get("skill"):
            warnings.append(f"Milestone {i+1}: missing skill field")

    valid_categories = {"Foundation", "Core Domain", "Industry", "Emerging"}
    for ms in milestones:
        cat = ms.get("category", "")
        if cat and cat not in valid_categories:
            warnings.append(f"Unknown category '{cat}' in '{ms.get('milestone_title','?')}'")

    for ms in milestones:
        title = (ms.get("milestone_title") or "").lower()
        skill = (ms.get("skill") or "").lower()
        for marker in CSE_POLLUTION_MARKERS:
            if marker in title or marker in skill:
                issues.append(f"ERP CONTAMINATION in milestone: '{ms.get('milestone_title')}'")

    return issues, warnings


def run():
    # Make sure we import inside run() to avoid caching problems
    from job_search_ai.agents.career_trend.schemas import StudentProfile
    from job_search_ai.agents.career_trend.agent import CareerTrendAgent
    from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
    from job_search_ai.agents.skill_agent.schemas import SkillRequest
    from nexedu.path_finder.api.path_enrollment import enroll_student

    results = []
    total_issues = 0
    total_warnings = 0

    print("=" * 70)
    print("   COMPREHENSIVE AGENT VALIDATION — 20 DIVERSE PROFILES")
    print("=" * 70)

    for prof in PROFILES:
        pid = prof["id"]
        degree = prof["degree"]
        branch = prof["branch"]
        year = prof["year"]
        interests = prof["interests"]
        skills_declared = prof["skills"]

        # CRITICAL: Reconnect to DB at the start of each iteration to avoid idle timeouts
        try:
            frappe.db.close()
            frappe.db.connect()
        except Exception as e:
            print(f"  Warning: failed to reconnect db: {e}")

        print(f"\n{'─' * 70}")
        print(f"[ID={pid}] {degree} / {branch} | Year {year} | Interests: {', '.join(interests)}")
        print(f"  Declared skills: {skills_declared}")

        result = {
            "id": pid,
            "degree": degree,
            "branch": branch,
            "career_trend_recs": [],
            "skill_profile": None,
            "enrollment_status": None,
            "milestones_count": 0,
            "issues": [],
            "warnings": [],
            "errors": [],
        }

        # ── Step 1: CareerTrendAgent ──────────────────────────────────────
        try:
            t0 = time.perf_counter()
            student = StudentProfile(
                degree=degree,
                branch=branch,
                year=year,
                country="India",
                interests=interests,
                skills=skills_declared,
            )
            agent = CareerTrendAgent()
            resp = agent.run(student)
            elapsed = time.perf_counter() - t0

            recs = resp.recommended_paths[:3]
            career_names = [r.career for r in recs]
            confidences = [r.confidence for r in recs]
            result["career_trend_recs"] = career_names

            print(f"\n  [CareerTrendAgent] {elapsed:.1f}s")
            if career_names:
                for c, conf in zip(career_names, confidences):
                    print(f"    → {c} ({conf}% confidence)")
            else:
                print(f"    → NO recommendations (empty response)")
                result["warnings"].append("CareerTrendAgent returned 0 recommendations — knowledge base may need more data for this profile type")

        except Exception as e:
            err = f"CareerTrendAgent EXCEPTION: {str(e)[:200]}"
            result["errors"].append(err)
            print(f"  ✗ {err}")
            results.append(result)
            total_issues += 1
            continue

        # ── Step 2: SkillAgent — validate top recommended career ──────────
        top_career = career_names[0] if career_names else None

        # Fallback role mapping if agent returns nothing
        if not top_career:
            interest_to_role = {
                "Data Science": "Data Scientist",
                "Research": "Research Analyst",
                "Pharmaceuticals": "Pharmaceutical Researcher",
                "Biotechnology": "Biotechnologist",
                "Analytics": "Data Analyst",
                "Finance": "Financial Analyst",
                "Accounting": "Chartered Accountant",
                "Investment": "Investment Analyst",
                "Digital Marketing": "Digital Marketing Specialist",
                "Business Analytics": "Business Analyst",
                "Business": "Business Development Manager",
                "Entrepreneurship": "Entrepreneur",
                "Human Resources": "HR Manager",
                "Content Writing": "Content Writer",
                "Counselling": "Psychologist",
                "Marketing": "Marketing Manager",
                "Agriculture": "Agriculture Specialist",
                "Agri Technology": "Agri-Tech Specialist",
                "Healthcare": "Healthcare Analyst",
                "Data Analytics": "Data Analyst",
            }
            for interest in interests:
                if interest in interest_to_role:
                    top_career = interest_to_role[interest]
                    break
            if top_career:
                print(f"    (No recommendation returned — testing SkillAgent for fallback role: '{top_career}')")

        if top_career:
            try:
                t0 = time.perf_counter()
                sk_agent = SkillAgent()
                sk_req = SkillRequest(role=top_career)
                sk_res = sk_agent.run(sk_req, save_to_doctype=False)
                elapsed = time.perf_counter() - t0
                prof_data = sk_res.profile

                result["skill_profile"] = {
                    "role": prof_data.role_name,
                    "source": prof_data.source,
                    "foundation": prof_data.foundation_skills,
                    "core_domain": prof_data.core_domain_skills,
                    "industry": prof_data.industry_skills,
                    "emerging": prof_data.emerging_skills,
                }

                print(f"\n  [SkillAgent] {elapsed:.1f}s (src={prof_data.source}) → {top_career}")
                print(f"    Foundation  ({len(prof_data.foundation_skills)}): {prof_data.foundation_skills}")
                print(f"    Core Domain ({len(prof_data.core_domain_skills)}): {prof_data.core_domain_skills}")
                print(f"    Industry    ({len(prof_data.industry_skills)}): {prof_data.industry_skills}")
                print(f"    Emerging    ({len(prof_data.emerging_skills)}): {prof_data.emerging_skills}")

                sk_issues, sk_warnings = validate_skill_profile(prof_data, top_career)
                result["issues"].extend(sk_issues)
                result["warnings"].extend(sk_warnings)
                if sk_issues:
                    for iss in sk_issues:
                        print(f"    ✗ SKILL ISSUE: {iss}")
                if sk_warnings:
                    for w in sk_warnings:
                        print(f"    ⚠  SKILL WARN: {w}")

            except Exception as e:
                err = f"SkillAgent EXCEPTION for '{top_career}': {str(e)[:200]}"
                result["errors"].append(err)
                print(f"  ✗ {err}")
        else:
            result["warnings"].append("No career role determined — skipping SkillAgent + RoadmapAgent")
            results.append(result)
            continue

        # ── Step 3: Enrollment + RoadmapAgent ────────────────────────────
        test_student = f"test_profile_{pid}@teststridenex.com"

        try:
            # Ensure test student exists with all required fields
            if not frappe.db.exists("Student", test_student):
                frappe.get_doc({
                    "doctype": "Student",
                    "first_name": "TestProfile",
                    "last_name": str(pid),
                    "email_id": test_student,
                    "student_name": f"Test Profile {pid}",
                    "college": "Tanvi International",
                }).insert(ignore_permissions=True)

            # Clean up prior test data
            frappe.db.delete("Student Path Enrollment", {"student": test_student})
            frappe.db.delete("Student Skill", {"student": test_student})
            frappe.db.commit()

            for sk in skills_declared:
                if not frappe.db.exists("Skill", sk):
                    try:
                        frappe.get_doc({"doctype": "Skill", "skill_name": sk}).insert(ignore_permissions=True)
                    except Exception:
                        pass
                frappe.get_doc({
                    "doctype": "Student Skill",
                    "student": test_student,
                    "skill": sk,
                    "current_level": "Intermediate",
                    "ai_verified": 1,
                    "status": "Verified",
                }).insert(ignore_permissions=True)
            frappe.db.commit()

            t0 = time.perf_counter()
            enroll_res = enroll_student(
                student=test_student,
                career_path=top_career,
                path_generation_mode="AI"
            )
            elapsed = time.perf_counter() - t0

            result["enrollment_status"] = enroll_res.get("status")
            enrollment_name = enroll_res.get("enrollment")
            print(f"\n  [RoadmapAgent] {elapsed:.1f}s → {enrollment_name} ({enroll_res.get('status')})")

            if enrollment_name:
                enrollment_doc = frappe.get_doc("Student Path Enrollment", enrollment_name)
                milestones = [
                    {
                        "milestone_title": m.milestone_title,
                        "category": m.category,
                        "skill": m.skill,
                        "milestone_order": m.milestone_order,
                        "duration_days": getattr(m, "duration_days", None),
                    }
                    for m in (enrollment_doc.milestone_progress or [])
                ]
                result["milestones_count"] = len(milestones)

                print(f"    Milestones: {len(milestones)}")
                for ms in milestones[:6]:
                    print(f"      [{ms.get('category','?'):12s}] {ms.get('milestone_title','?')}")
                if len(milestones) > 6:
                    print(f"      ... and {len(milestones)-6} more")

                ms_issues, ms_warnings = validate_milestones(milestones, top_career)
                result["issues"].extend(ms_issues)
                result["warnings"].extend(ms_warnings)
                if ms_issues:
                    for iss in ms_issues:
                        print(f"    ✗ MILESTONE ISSUE: {iss}")
                if ms_warnings:
                    for w in ms_warnings:
                        print(f"    ⚠  MILESTONE WARN: {w}")

        except Exception as e:
            err = f"Enrollment/Roadmap EXCEPTION for '{top_career}': {str(e)[:300]}"
            result["errors"].append(err)
            print(f"  ✗ {err}")
        finally:
            try:
                frappe.db.delete("Student Path Enrollment", {"student": test_student})
                frappe.db.delete("Student Skill", {"student": test_student})
                frappe.db.commit()
            except Exception:
                pass

        # Tally
        profile_issues = len(result["issues"])
        profile_warnings = len(result["warnings"])
        profile_errors = len(result["errors"])
        total_issues += profile_issues + profile_errors
        total_warnings += profile_warnings

        icon = "✓" if (profile_issues == 0 and profile_errors == 0) else "✗"
        print(f"\n  {icon} Profile {pid} result — Issues: {profile_issues}, Warnings: {profile_warnings}, Errors: {profile_errors}")
        results.append(result)

    # ── FINAL REPORT ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("   VALIDATION SUMMARY REPORT")
    print("=" * 70)

    passed = sum(1 for r in results if not r["issues"] and not r["errors"])
    failed = len(results) - passed
    print(f"\n  PASSED: {passed}/{len(results)}  |  FAILED: {failed}/{len(results)}")
    print(f"  Total Issues: {total_issues}  |  Total Warnings: {total_warnings}")
    print()
    print(f"  {'ID':<5} {'Degree/Branch':<35} {'Top Career':<30} {'MS':>3} {'I':>3} {'W':>3}")
    print(f"  {'─'*5} {'─'*35} {'─'*30} {'─'*3} {'─'*3} {'─'*3}")
    for r in results:
        icon = "✓" if (not r["issues"] and not r["errors"]) else "✗"
        top = (r["career_trend_recs"][0] if r["career_trend_recs"] else
               (r["skill_profile"]["role"] if r["skill_profile"] else "N/A"))
        label = f"{r['degree'][:15]}/{r['branch'][:18]}"
        print(f"  {icon} {r['id']:<4} {label:<35} {top[:30]:<30} {r['milestones_count']:>3} {len(r['issues']):>3} {len(r['warnings']):>3}")

    # Highlight all issues
    any_issues = any(r["issues"] or r["errors"] for r in results)
    if any_issues:
        print("\n  ── DETAILED ISSUES ──")
        for r in results:
            if r["issues"] or r["errors"]:
                print(f"\n  [ID={r['id']}] {r['degree']}/{r['branch']}:")
                for iss in r["issues"]:
                    print(f"    ✗ {iss}")
                for err in r["errors"]:
                    print(f"    ✗ ERROR: {err}")

    print("\n" + "=" * 70)
    print("   TEST RUN COMPLETE")
    print("=" * 70)
