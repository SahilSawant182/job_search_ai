from __future__ import annotations

import time
import frappe
from job_search_ai.agents.roadmap_agent.agent import RoadmapAgent
from job_search_ai.services.skill_gap.service import SkillGapService

def run_audit():
    """
    Executes the manual roadmap audit against 5 key careers:
    - AI Engineer
    - Frontend Developer
    - DevOps Engineer
    - Data Engineer
    - Frappe Developer
    """
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

    print("\n" + "="*80)
    print("STARTING ROADMAP AGENT MANUAL AUDIT")
    print("="*80)

    for career in careers:
        print(f"\n--- Career: {career} ---")
        try:
            # Ensure DB connection is active (LLM calls can take time, causing timeout)
            try:
                frappe.db.connect()
            except Exception:
                pass

            # 1. Compute Skill Gap
            gap_report = service.get_skill_gap_report(student_email, career)
            gap_dict = gap_report.to_dict()

            print(f"Readiness Score: {gap_report.readiness_score}%")
            print(f"Matched Skills: {gap_report.matched_skills}")
            print(f"Missing Foundation: {gap_report.missing_foundation}")
            print(f"Missing Core Domain: {gap_report.missing_core_domain}")
            print(f"Missing Industry: {gap_report.missing_industry}")
            print(f"Missing Emerging: {gap_report.missing_emerging}")

            # Ensure DB is connected before agent run
            try:
                frappe.db.connect()
            except Exception:
                pass

            # 2. Run RoadmapAgent
            t0 = time.perf_counter()
            result = agent.run(student_email, career, gap_dict)
            elapsed = time.perf_counter() - t0

            # 3. Print Results
            print(f"Validation Status: {result.validation_status}")
            if result.error_message:
                print(f"Error Message: {result.error_message}")
            
            print(f"Execution Time: {elapsed:.2f}s (LLM time: {result.metrics.get('llm_time', 0.0)}s)")
            
            milestones = result.roadmap.milestones
            print(f"Generated Milestones ({len(milestones)}):")
            
            generated_skills = []
            for m in milestones:
                print(f"  - [{m.sequence}] {m.title} ({m.skill_tier}) -> Skill: {m.skill} (Duration: {m.duration_days} days)")
                print(f"    Objective: {m.objective}")
                print(f"    Project: {m.project}")
                generated_skills.append(m.skill.lower().strip())

            # Verify coverage and incorrect generations
            missing_skills = [
                s.lower().strip() for s in (
                    gap_report.missing_foundation +
                    gap_report.missing_core_domain +
                    gap_report.missing_industry +
                    gap_report.missing_emerging
                )
            ]
            
            covered = [s for s in missing_skills if s in generated_skills]
            incorrect = [s for s in generated_skills if s not in missing_skills]
            ignored_matched = [s for s in generated_skills if s in [m.lower().strip() for m in gap_report.matched_skills]]

            print(f"Covered Missing Skills: {len(covered)}/{len(missing_skills)}")
            print(f"Incorrectly Generated Skills: {incorrect}")
            print(f"Ignored Matched Skills: {ignored_matched}")

        except Exception as exc:
            print(f"Audit failed for career '{career}': {exc}")
            import traceback
            traceback.print_exc()

    # Reconnect at the end to allow bench execute to finish commit cleanly
    try:
        frappe.db.connect()
    except Exception:
        pass

    print("\n" + "="*80)
    print("AUDIT COMPLETE")
    print("="*80 + "\n")
