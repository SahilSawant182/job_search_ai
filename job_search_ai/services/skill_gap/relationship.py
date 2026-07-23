# -*- coding: utf-8 -*-
# job_search_ai/services/skill_gap/relationship.py

import logging
from typing import Dict, Set, List
import frappe
from job_search_ai.services.skill_gap.normalizer import get_skill_key

logger = logging.getLogger(__name__)

# Constants for Relation Types
RELATION_ALIAS = "Alias"
RELATION_CONTAINS = "Contains"
RELATION_RELATED = "Related"
RELATION_PREREQUISITE = "Prerequisite"

# Adjacency list of implications: skill_key -> Set of implied canonical skill names
_RELATIONSHIP_CACHE: Dict[str, Set[str]] = {}
_INITIALIZED = False


# Default minimum confidence for non-trusted sources (can be overridden via settings)
_DEFAULT_CONFIDENCE_THRESHOLD = 0.0


def initialize_relationship_cache(force: bool = False) -> None:
    """
    Populate the relationship implication cache from the active Skill Relationship records.

    Trust policy (per record):
    - is_trusted_source = True  → always loaded, confidence is ignored.
    - is_trusted_source = False → only loaded if confidence >= threshold.

    This makes trust configurable per-record: curated imports (ESCO, O*NET) can
    be marked trusted by an admin even though their source_type is 'Imported'.
    """
    global _RELATIONSHIP_CACHE, _INITIALIZED
    if _INITIALIZED and not force:
        return

    _RELATIONSHIP_CACHE.clear()

    # Confidence threshold for non-trusted (LLM/Imported) relationships
    confidence_threshold = _DEFAULT_CONFIDENCE_THRESHOLD
    try:
        if getattr(frappe, "db", None) and frappe.db.exists("DocType", "Job Search AI Settings"):
            meta = frappe.get_meta("Job Search AI Settings")
            if meta.has_field("skill_relationship_confidence_threshold"):
                val = frappe.db.get_single_value("Job Search AI Settings", "skill_relationship_confidence_threshold")
                if val is not None:
                    confidence_threshold = float(val)
    except Exception:
        pass

    try:
        if getattr(frappe, "db", None) and hasattr(frappe.db, "get_all"):
            # Load all active and approved skill relationships (confidence filtering done per-record)
            records = frappe.get_all(
                "Skill Relationship",
                filters={"active": 1, "status": "Approved"},
                fields=["from_skill", "relation_type", "to_skill", "is_trusted_source", "confidence"]
            )
            for r in records:
                from_skill = r.get("from_skill")
                relation_type = r.get("relation_type")
                to_skill = r.get("to_skill")
                source_type = r.get("source_type") or "Manual"
                is_trusted = bool(r.get("is_trusted_source", 1))
                confidence = r.get("confidence") or 1.0

                if not from_skill or not to_skill:
                    continue

                # Trusted relationships are always cached.
                # Untrusted (e.g. raw LLM suggestions) must meet the confidence threshold.
                if not is_trusted and confidence < confidence_threshold:
                    logger.debug(
                        "SkillRelationshipCache: skipping low-confidence relationship "
                        "%r -> %r (source=%s confidence=%.2f threshold=%.2f)",
                        from_skill, to_skill, source_type, confidence, confidence_threshold
                    )
                    continue

                from_key = get_skill_key(from_skill)
                to_key = get_skill_key(to_skill)

                if not from_key or not to_key:
                    continue

                # Implication rules:
                # 1. Alias: bidirectional (A implies B, B implies A)
                if relation_type == RELATION_ALIAS:
                    _add_implication(from_key, to_skill)
                    _add_implication(to_key, from_skill)
                # 2. Contains (parent contains child): parent implies child (parent -> child)
                elif relation_type == RELATION_CONTAINS:
                    _add_implication(from_key, to_skill)

    except Exception:
        # Prevent errors in non-db or bootstrap environments
        pass

    _INITIALIZED = True
    logger.info("SkillRelationshipCache: initialized cache with %d entries", len(_RELATIONSHIP_CACHE))


def _add_implication(source_key: str, target_name: str) -> None:
    if source_key not in _RELATIONSHIP_CACHE:
        _RELATIONSHIP_CACHE[source_key] = set()
    _RELATIONSHIP_CACHE[source_key].add(target_name)


def invalidate_relationship_cache() -> None:
    """
    Force reload the relationship cache.
    """
    global _INITIALIZED
    _INITIALIZED = False
    initialize_relationship_cache(force=True)


def expand_skill_relations(skill_name: str) -> Set[str]:
    """
    Expand a canonical skill name through the relationship graph.
    Returns all implied/equivalent skills (including the skill itself).
    Includes cycle detection and logs a warning if a cycle is detected.
    """
    if not skill_name or not skill_name.strip():
        return set()

    initialize_relationship_cache()

    start_skill = skill_name.strip()
    start_key = get_skill_key(start_skill)
    if not start_key:
        return {start_skill}

    visited: Set[str] = set()
    expanded_skills: Set[str] = {start_skill}
    rec_stack: List[str] = []

    def dfs(curr_skill: str):
        curr_key = get_skill_key(curr_skill)
        if not curr_key:
            return

        if curr_key in rec_stack:
            logger.warning(
                "SkillRelationship: cycle detected in graph path: %s -> %s",
                " -> ".join(rec_stack),
                curr_key
            )
            return

        if curr_key in visited:
            return

        visited.add(curr_key)
        rec_stack.append(curr_key)

        implied_targets = _RELATIONSHIP_CACHE.get(curr_key, set())
        for target in implied_targets:
            expanded_skills.add(target)
            dfs(target)

        rec_stack.pop()

    dfs(start_skill)
    return expanded_skills
