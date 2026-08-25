from __future__ import annotations
import logging
from typing import List, Tuple
from job_search_ai.agents.roadmap_agent.schemas import RoadmapProfile, RoadmapMilestone

logger = logging.getLogger(__name__)

def validate_roadmap(
    roadmap: RoadmapProfile,
    requested_career: str,
    skill_gap: dict
) -> Tuple[bool, str | None]:
    """
    Deterministically validates the generated roadmap against the 10 critical rules.
    Returns (is_valid, error_message).
    """
    missing_foundation = set(skill_gap.get("missing_foundation") or [])
    missing_core = set(skill_gap.get("missing_core_domain") or [])
    missing_industry = set(skill_gap.get("missing_industry") or [])
    missing_emerging = set(skill_gap.get("missing_emerging") or [])
    matched_skills = set(skill_gap.get("matched_skills") or [])
    
    all_missing_skills = missing_foundation | missing_core | missing_industry | missing_emerging
    
    # Rule 2: Career consistency
    if roadmap.career.lower().strip() != requested_career.lower().strip():
        return False, f"Career mismatch: requested '{requested_career}', got '{roadmap.career}'"

    # If the skill gap is empty, milestones should be empty
    if not all_missing_skills:
        if roadmap.milestones:
            return False, "Roadmap contains milestones but student has no missing skills"
        return True, None

    # Track seen sequences, skills, etc.
    seen_sequences = set()
    seen_skills = set()
    expected_sequence = 1
    
    allowed_types = {"Learn", "Build", "Assess", "Apply", "Connect"}
    allowed_tiers = {"Foundation", "Core Domain", "Industry", "Emerging"}

    # Map of skill to its tier from gap report (case-insensitive key comparison)
    skill_to_tier_map = {}
    for s in missing_foundation:
        skill_to_tier_map[s.lower().strip()] = "Foundation"
    for s in missing_core:
        skill_to_tier_map[s.lower().strip()] = "Core Domain"
    for s in missing_industry:
        skill_to_tier_map[s.lower().strip()] = "Industry"
    for s in missing_emerging:
        skill_to_tier_map[s.lower().strip()] = "Emerging"

    for m in roadmap.milestones:
        # Rule 7: Positive duration
        if m.duration_days <= 0:
            return False, f"Milestone '{m.title}' has invalid duration: {m.duration_days}"

        # Rule 8: Valid milestone type
        if m.type not in allowed_types:
            return False, f"Milestone '{m.title}' has invalid type: {m.type}"

        # Rule 9: Sequence consistency
        if m.sequence in seen_sequences:
            return False, f"Duplicate sequence number: {m.sequence}"
        if m.sequence != expected_sequence:
            return False, f"Non-consecutive sequence: expected {expected_sequence}, got {m.sequence}"
        seen_sequences.add(m.sequence)
        expected_sequence += 1

        skill_key = m.skill.lower().strip()

        # Rule 4: No matched skills
        if skill_key in {s.lower().strip() for s in matched_skills}:
            return False, f"Milestone '{m.title}' targets already matched skill: {m.skill}"

        # Rule 3: Skill validity
        if skill_key not in {s.lower().strip() for s in all_missing_skills}:
            return False, f"Milestone '{m.title}' targets skill not in gap report: {m.skill}"

        # Rule 5: No duplicate skills
        if skill_key in seen_skills:
            return False, f"Duplicate target skill in roadmap: {m.skill}"
        seen_skills.add(skill_key)

        # Rule 6: Tier consistency
        if m.skill_tier not in allowed_tiers:
            return False, f"Milestone '{m.title}' has invalid tier: {m.skill_tier}"
        expected_tier = skill_to_tier_map.get(skill_key)
        if expected_tier and m.skill_tier.lower().strip() != expected_tier.lower().strip():
            return False, f"Tier mismatch for '{m.skill}': expected '{expected_tier}', got '{m.skill_tier}'"

        # Rule 10: Non-empty objectives / projects
        if not m.title or not m.title.strip():
            return False, f"Milestone sequence {m.sequence} has empty title"
        if not m.objective or not m.objective.strip():
            return False, f"Milestone '{m.title}' has empty objective"
        if not m.project or not m.project.strip():
            return False, f"Milestone '{m.title}' has empty practical project description"

        # Rule 11: Non-empty completion_criteria
        if not m.completion_criteria or not isinstance(m.completion_criteria, list) or len(m.completion_criteria) == 0:
            return False, f"Milestone '{m.title}' has empty completion_criteria"

        # Rule 12: Non-empty learning_outcomes
        if not m.learning_outcomes or not isinstance(m.learning_outcomes, list) or len(m.learning_outcomes) == 0:
            return False, f"Milestone '{m.title}' has empty learning_outcomes"

        # Rule 13: supporting_skills list check
        if not isinstance(m.supporting_skills, list):
            return False, f"Milestone '{m.title}' has invalid supporting_skills list"

    # Coverage check: Verify all missing core domain skills are covered or in uncovered_skills
    covered_skills = {m.skill.lower().strip() for m in roadmap.milestones if m.skill}
    uncovered_skills_in_roadmap = {u.skill.lower().strip() for u in roadmap.uncovered_skills if u.skill}
    missing_accounted = covered_skills | uncovered_skills_in_roadmap

    unaccounted_core = [s for s in missing_core if s.lower().strip() not in missing_accounted]
    if unaccounted_core:
        logger.warning(
            "Validation failed for Core Domain coverage. milestones: %r, uncovered: %r, missing_accounted: %r, missing_core: %r",
            covered_skills, uncovered_skills_in_roadmap, missing_accounted, missing_core
        )
        return False, f"Missing Core Domain skills not covered in milestones or uncovered_skills: {', '.join(unaccounted_core)}"

    unaccounted_other = [s for s in all_missing_skills if s.lower().strip() not in missing_accounted]
    if unaccounted_other:
        logger.warning(
            "Validation failed for overall coverage. milestones: %r, uncovered: %r, missing_accounted: %r, all_missing_skills: %r",
            covered_skills, uncovered_skills_in_roadmap, missing_accounted, all_missing_skills
        )
        return False, f"Missing skills not covered in milestones or uncovered_skills: {', '.join(unaccounted_other)}"

    return True, None
