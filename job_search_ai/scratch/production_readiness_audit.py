from __future__ import annotations
import frappe
import time
from job_search_ai.agents.roadmap_agent.agent import RoadmapAgent
from job_search_ai.services.skill_gap.service import SkillGapService

def run_production_audit():
    student_email = "demo_student@example.com"
    careers = [
        "AI Engineer",
        "Frontend Developer",
        "DevOps Engineer for Web Applications",
        "Data Scientist",
        "Frappe Developer"
    ]

    agent = RoadmapAgent()
    service = SkillGapService()

    # Get student skills
    student_skills = [s.skill for s in frappe.get_all('Student Skill', filters={'student': student_email}, fields=['skill'])]

    for career in careers:
        print(f"==================================================")
        print(f"Career: {career}")
        print(f"Student Skills: {student_skills}")
        
        # Ensure DB is active
        try:
            frappe.db.connect()
        except Exception:
            pass

        # 1. Skill Gap Report
        gap_report = service.get_skill_gap_report(student_email, career)
        gap_dict = gap_report.to_dict()
        
        matched_skills = gap_report.matched_skills
        missing_foundation = gap_report.missing_foundation
        missing_core_domain = gap_report.missing_core_domain
        missing_industry = gap_report.missing_industry
        missing_emerging = gap_report.missing_emerging

        print(f"Matched Skills: {matched_skills}")
        print(f"Missing Foundation: {missing_foundation}")
        print(f"Missing Core Domain: {missing_core_domain}")
        print(f"Missing Industry: {missing_industry}")
        print(f"Missing Emerging: {missing_emerging}")

        # 2. Roadmap Agent Generation
        try:
            frappe.db.connect()
        except Exception:
            pass
        
        result = agent.run(student_email, career, gap_dict)
        print(f"Validation Status: {result.validation_status}")
        if result.error_message:
            print(f"Error Message: {result.error_message}")
        
        milestones = result.roadmap.milestones
        generated_skills = [m.skill for m in milestones]
        print(f"Generated Roadmap Skills: {generated_skills}")

        # --- Calculations ---
        # Matched-skill contamination
        contamination = [s for s in generated_skills if s.lower().strip() in [m.lower().strip() for m in matched_skills]]
        print(f"Matched-skill contamination: {len(contamination)}")
        if contamination:
            print(f"Contaminated skills: {contamination}")

        # Missing-skill coverage
        missing_skills_lower = [s.lower().strip() for s in (missing_foundation + missing_core_domain + missing_industry + missing_emerging)]
        generated_skills_lower = [s.lower().strip() for s in generated_skills]
        
        missing_count = len(missing_skills_lower)
        covered = [s for s in missing_skills_lower if s in generated_skills_lower]
        covered_count = len(covered)
        coverage_pct = (covered_count / missing_count * 100.0) if missing_count > 0 else 100.0
        uncovered = [s for s in missing_skills_lower if s not in generated_skills_lower]

        print(f"missing skill count: {missing_count}")
        print(f"covered skill count: {covered_count}")
        print(f"coverage percentage: {coverage_pct:.1f}%")
        print(f"uncovered skills: {uncovered}")

        # Tier Correctness
        tier_mismatch_count = 0
        skill_to_tier_map = {}
        for s in missing_foundation:
            skill_to_tier_map[s.lower().strip()] = "Foundation"
        for s in missing_core_domain:
            skill_to_tier_map[s.lower().strip()] = "Core Domain"
        for s in missing_industry:
            skill_to_tier_map[s.lower().strip()] = "Industry"
        for s in missing_emerging:
            skill_to_tier_map[s.lower().strip()] = "Emerging"

        for m in milestones:
            expected_tier = skill_to_tier_map.get(m.skill.lower().strip())
            if expected_tier and m.skill_tier != expected_tier:
                print(f"Tier mismatch: Skill '{m.skill}' expected tier '{expected_tier}', got '{m.skill_tier}'")
                tier_mismatch_count += 1
        print(f"Tier mismatches: {tier_mismatch_count}")

        # Duplicate Audit
        titles = [m.title for m in milestones]
        skills = [m.skill for m in milestones]
        seqs = [m.sequence for m in milestones]
        empty_skills = [m for m in milestones if not m.skill]

        dup_titles = len(titles) - len(set(titles))
        dup_skills = len(skills) - len(set(skills))
        dup_seqs = len(seqs) - len(set(seqs))
        
        # check gaps in sequence numbers
        sorted_seqs = sorted(seqs)
        expected_seqs = list(range(1, len(milestones) + 1))
        seq_gaps = [x for x in expected_seqs if x not in sorted_seqs]

        print(f"duplicate milestone titles: {dup_titles}")
        print(f"duplicate target skills: {dup_skills}")
        print(f"duplicate sequence: {dup_seqs}")
        print(f"gaps in sequence numbers: {seq_gaps}")
        print(f"milestones with empty skills: {len(empty_skills)}")
        
        # Roadmap Quality Check
        quality_failures = 0
        for m in milestones:
            if not m.title or not m.type or not m.skill or not m.skill_tier or m.duration_days <= 0 or not m.objective or not m.project:
                print(f"Quality check failed for milestone sequence {m.sequence}: title={m.title!r}, type={m.type!r}, skill={m.skill!r}, tier={m.skill_tier!r}, duration={m.duration_days!r}, objective={m.objective!r}, project={m.project!r}")
                quality_failures += 1
        print(f"Quality failures: {quality_failures}")
        print(f"==================================================\n")

if __name__ == '__main__':
    run_production_audit()
