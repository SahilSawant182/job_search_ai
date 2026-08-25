from __future__ import annotations
import frappe

def get_career_path_context(career: str) -> dict | None:
    """
    Look up Career Path in Frappe database. If found, returns the baseline
    prerequisites and milestones to provide templating/duration context to the LLM.
    """
    if not frappe.db.exists("Career Path", career):
        return None
    try:
        doc = frappe.get_doc("Career Path", career)
        context = {
            "name": doc.name,
            "path_name": doc.path_name,
            "difficulty_level": doc.difficulty_level,
            "estimated_duration_months": doc.estimated_duration_months,
            "prerequisites": [
                {"skill": p.prerequisite_skills, "level": p.level}
                for p in doc.prerequisite_skills
            ],
            "milestones": [
                {
                    "title": m.milestone_title,
                    "type": m.milestone_type,
                    "skill": m.skill,
                    "required_level": m.required_skill_level,
                    "duration_days": m.duration_days,
                    "points": [pt.strip() for pt in (m.milestone_points or "").split("\n") if pt.strip()]
                }
                for m in doc.path_milestone
            ]
        }
        return context
    except Exception:
        return None

def get_prerequisites_dag(missing_skills: list[str]) -> str:
    """
    Finds all active and approved 'Prerequisite' relationships between any of the missing skills
    and returns a structured string that can be injected into the prompt.
    """
    if not missing_skills:
        return "SKILL DEPENDENCIES:\n- None"
    
    try:
        records = frappe.get_all(
            "Skill Relationship",
            filters={
                "from_skill": ["in", missing_skills],
                "to_skill": ["in", missing_skills],
                "relation_type": "Prerequisite",
                "active": 1,
                "status": "Approved"
            },
            fields=["from_skill", "to_skill"]
        )
    except Exception:
        records = []
    
    if not records:
        return "SKILL DEPENDENCIES:\n- None"
        
    deps = {}
    for r in records:
        parent = r["from_skill"]
        child = r["to_skill"]
        if child not in deps:
            deps[child] = []
        if parent not in deps[child]:
            deps[child].append(parent)
            
    lines = ["SKILL DEPENDENCIES:"]
    for child, parents in deps.items():
        lines.append(f"  {child}")
        lines.append("    prerequisite:")
        for p in parents:
            lines.append(f"      - {p}")
            
    return "\n".join(lines)

def build_roadmap_prompt(
    career: str,
    skill_gap: dict,
    career_context: dict | None = None,
    student_context: dict | None = None
) -> str:
    """Builds a highly detailed prompt instructing the LLM to generate the roadmap JSON."""
    missing_foundation = skill_gap.get("missing_foundation") or []
    missing_core = skill_gap.get("missing_core_domain") or []
    missing_industry = skill_gap.get("missing_industry") or []
    missing_emerging = skill_gap.get("missing_emerging") or []
    matched = skill_gap.get("matched_skills") or []
    
    all_missing_skills = list(missing_foundation) + list(missing_core) + list(missing_industry) + list(missing_emerging)

    def format_bullets(lst):
        if not lst:
            return "  * None"
        return "\n".join(f"  * {item}" for item in lst)

    # Build the explicit mappings list
    explicit_mappings = []
    for s in missing_foundation:
        explicit_mappings.append(f'- Skill "{s}" -> MUST set "skill": "{s}" and "skill_tier": "Foundation"')
    for s in missing_core:
        explicit_mappings.append(f'- Skill "{s}" -> MUST set "skill": "{s}" and "skill_tier": "Core Domain"')
    for s in missing_industry:
        explicit_mappings.append(f'- Skill "{s}" -> MUST set "skill": "{s}" and "skill_tier": "Industry"')
    for s in missing_emerging:
        explicit_mappings.append(f'- Skill "{s}" -> MUST set "skill": "{s}" and "skill_tier": "Emerging"')

    explicit_mappings_str = "\n".join(explicit_mappings) if explicit_mappings else "- None"

    dag_str = get_prerequisites_dag(all_missing_skills)

    student_info_str = ""
    if student_context:
        student_info_str = f"""
STUDENT CONTEXT:
- Academic Year: {student_context.get('academic_year') or 'N/A'}
- CGPA: {student_context.get('cgpa') or 'N/A'}
- Course: {student_context.get('course') or 'N/A'}
- Department: {student_context.get('department') or 'N/A'}
- Career Interests/Focus Areas: {student_context.get('interests') or 'N/A'}

PERSONALIZATION GUIDELINE:
Tailor the milestone project descriptions, scenarios, and application areas to align with the student's academic background and career interests where possible.
"""
    else:
        student_info_str = """
STUDENT CONTEXT:
- Generic template run. Avoid any student-specific assumptions. Focus on generic, standard industry applications.
"""

    gap_summary = f"""
TARGET CAREER: {career}
SKILL GAP REPORT:
- Matched/Student already has (DO NOT GENERATE MILESTONES FOR THESE):
{format_bullets(matched)}

- Missing Foundation Skills:
{format_bullets(missing_foundation)}

- Missing Core Domain Skills:
{format_bullets(missing_core)}

- Missing Industry Skills:
{format_bullets(missing_industry)}

- Missing Emerging Skills:
{format_bullets(missing_emerging)}

STRICT REQUIRED FIELD VALUES (Use these exact names and tiers):
{explicit_mappings_str}

{dag_str}
{student_info_str}
"""

    context_summary = ""
    if career_context:
        context_summary = f"\nREFERENCE CAREER PATH TEMPLATE CONTEXT:\n"
        context_summary += f"Difficulty: {career_context.get('difficulty_level')}\n"
        context_summary += f"Estimated Duration: {career_context.get('estimated_duration_months')} Month(s)\n"
        context_summary += "Default Milestones:\n"
        for idx, m in enumerate(career_context.get("milestones", [])):
            context_summary += f"- {idx+1}. {m['title']} | Type: {m['type']} | Skill: {m['skill']} | Duration: {m['duration_days']} Days\n"

    prompt = f"""
You are the Pathfinder Roadmap Agent. Generate a personalized learning roadmap in JSON format for the career of '{career}', targeting only the student's missing skills.

{gap_summary}
{context_summary}

ROADMAP DECISION PRIORITY:
1. Never teach a matched skill as a missing skill.
2. Only target supplied missing skills.
3. Respect Skill Relationship prerequisites.
4. Respect Foundation → Core → Industry → Emerging progression.
5. Prioritize career-critical skills.
6. Build a logically progressive sequence.
7. Create practical projects that reinforce the target skill.
8. Estimate realistic durations.
9. Add optional enrichment only after required skills are covered.

RULES:
1. ZERO-REGRESSION: Never generate a milestone or checklist point for a matched/already-known skill.
2. CLOSED-WORLD RULE: The `skill` field of every milestone MUST exactly match one of the supplied `missing_*` skills after canonical normalization. Never invent, rename, merge, split, or introduce a new required skill.
3. PRIORITY RULE: Generate the smallest realistic sequence of milestones that moves the student toward career readiness. Prioritize critical missing skills and prerequisite dependencies. Do not create additional milestones merely to satisfy a coverage percentage.
4. AUTHORITATIVE PREREQUISITES: Treat supplied prerequisite relationships as authoritative. A prerequisite must never appear after the skill that depends on it. Do not invent conflicting prerequisite relationships.
5. UNCOVERED SKILLS & TOTAL COVERAGE: Every single missing skill listed in the SKILL GAP REPORT (Foundation, Core Domain, Industry, Emerging) MUST be accounted for. For every missing skill, you must either: (a) create a corresponding milestone in "milestones", OR (b) list it in the "uncovered_skills" array with a clear explanation of why it was skipped (e.g., due to prerequisite chains, time constraints, or learning sequence limits). You must NOT silently omit any missing skill from both.
6. ONE SKILL PER MILESTONE: Each milestone must target exactly ONE missing skill.
7. TIER COHERENCE: Use the exact skill_tier shown in STRICT REQUIRED FIELD VALUES.
8. VALID TYPES: Milestone type must be: "Learn", "Build", "Assess", "Apply", or "Connect".
9. DURATION: "duration_days" must be a positive integer (Foundation: 7-10, Core: 10-14, Industry: 12-18, Emerging: 7-12 days).
10. PROJECT CONSTRAINT: A project must primarily practice the milestone's target skill. Do not introduce unrelated technologies as mandatory project requirements unless they are already present in the supplied career skill profile or missing-skill list.
11. GRANULAR CHECKLIST: Provide exactly 3 to 4 specific, technical checklist items under "points". Keep them brief.
12. EXACT SKILL MATCH: The "skill" field in each milestone MUST be the exact, case-sensitive string from the Missing Skills list. Do not invent or alter skill names.
13. VERIFIABLE COMPLETION CRITERIA: Each milestone must have 2 to 3 objective, verifiable criteria under "completion_criteria" (e.g., "Build a working REST API with test coverage > 80%").
14. LEARNING OUTCOMES: Provide 2 to 3 concrete competency statements under "learning_outcomes" (e.g., "Able to build secure authentication endpoints").
15. SUPPORTING SKILLS: Under "supporting_skills", specify any secondary tools or concepts utilized in this milestone (e.g., Git, Docker, Postgres).

JSON OUTPUT FORMAT:
Return ONLY a valid JSON object matching the following structure. Do not output any surrounding chat or markdown blocks.
{{
  "career": "{career}",
  "readiness_score": {skill_gap.get("readiness_score", 0)},
  "milestones": [
    {{
      "sequence": 1,
      "title": "Milestone Title",
      "type": "Learn",
      "skill": "Skill Name",
      "skill_tier": "Core Domain",
      "duration_days": 14,
      "objective": "Detailed learning objective.",
      "project": "Hands-on project description.",
      "points": [
        "Sub-topic 1",
        "Sub-topic 2",
        "Sub-topic 3"
      ],
      "linked_resource_type": "Course",
      "linked_resource": "Course Name",
      "completion_criteria": [
        "Objective criteria 1",
        "Objective criteria 2"
      ],
      "learning_outcomes": [
        "Outcome 1",
        "Outcome 2"
      ],
      "supporting_skills": [
        "Supporting skill 1",
        "Supporting skill 2"
      ]
    }}
  ],
  "uncovered_skills": [
    {{
      "skill": "Skill Name",
      "reason": "Reason why it is not included"
    }}
  ]
}}
"""
    return prompt
