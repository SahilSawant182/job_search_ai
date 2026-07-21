# -*- coding: utf-8 -*-
"""
CareerValidationService — pure Python deterministic career validation.

Provides Level 1 universal career validation (is it a valid job title/profession?)
and Level 2 student relevance validation (is it domain-aligned with the student's branch?).
Runs 100% deterministically in Python with zero external LLM calls.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from job_search_ai.agents.career_trend.schemas import StudentProfile

logger = logging.getLogger(__name__)

# Valid job title suffixes / role nouns indicating a real profession
VALID_ROLE_NOUNS = {
    "developer", "engineer", "scientist", "architect", "analyst",
    "administrator", "consultant", "designer", "manager", "specialist",
    "officer", "technician", "lead", "researcher", "coordinator",
    "director", "strategist", "programmer", "tester", "auditor",
    "instructor", "practitioner", "handler", "operator", "mechanic",
    "gardener", "agronomist", "doctor", "nurse", "accountant",
    "lawyer", "advocate", "planner", "evaluator", "expert", "master"
}

# Raw technology/tool names that are NOT standalone job titles
RAW_TECHNOLOGIES = {
    "react", "java", "python", "docker", "springboot", "spring boot",
    "tensorflow", "keras", "html", "css", "javascript", "js", "sql",
    "linux", "git", "kubernetes", "aws", "azure", "node.js", "nodejs",
    "express", "mongodb", "c++", "c#", "flutter", "swift", "kotlin",
    "pandas", "numpy", "thermodynamics", "hvac", "fluid mechanics"
}

# Industry umbrella definitions for domain relevance check
TECH_KEYWORDS = {
    "computer", "cs", "cse", "it", "information", "software", "web",
    "systems", "network", "programming", "development", "data", "ai",
    "ml", "intelligence", "machine", "analytics", "database", "cloud",
    "devops", "security", "cyber", "full-stack", "frontend", "backend",
    "mobile", "embedded", "robotics", "nlp", "vision", "automation"
}

AGRICULTURE_KEYWORDS = {
    "hydroponic", "greenhouse", "gardener", "horticulture", "aquaponics",
    "cultivation", "agronomist", "farming", "crop", "soil", "botany", "plant"
}

MECHANICAL_KEYWORDS = {
    "mechanical", "automotive", "thermal", "hvac", "cad", "solidworks",
    "chassis", "powertrain", "manufacturing", "mechatronics"
}


import json
import os

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
)


class CareerValidationService:
    """
    Validates career names and student relevance deterministically using JSON configs.
    """

    def __init__(self) -> None:
        self.role_nouns: set[str] = self._load_role_nouns()
        self.rejected_tech: set[str] = self._load_rejected_tech()
        self.rejected_phrases: set[str] = self._load_rejected_phrases()
        self.domain_map: dict[str, list[str]] = self._load_domain_map()

    def _load_role_nouns(self) -> set[str]:
        path = os.path.join(_CONFIG_DIR, "validator_config.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {r.lower().strip() for r in data.get("valid_role_nouns", [])}
            except Exception as exc:
                logger.warning("CareerValidationService: failed loading role nouns (%s)", exc)
        return VALID_ROLE_NOUNS

    def _load_rejected_tech(self) -> set[str]:
        path = os.path.join(_CONFIG_DIR, "validator_config.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {t.lower().strip() for t in data.get("rejected_tech_tokens", [])}
            except Exception as exc:
                logger.warning("CareerValidationService: failed loading tech tokens (%s)", exc)
        return RAW_TECHNOLOGIES

    def _load_rejected_phrases(self) -> set[str]:
        path = os.path.join(_CONFIG_DIR, "validator_config.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {p.lower().strip() for p in data.get("rejected_phrase_indicators", [])}
            except Exception as exc:
                logger.warning("CareerValidationService: failed loading phrase indicators (%s)", exc)
        return set()

    def _load_domain_map(self) -> dict[str, list[str]]:
        path = os.path.join(_CONFIG_DIR, "domain_mapping.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {k.lower().strip(): [v.lower() for v in val] for k, val in data.items()}
            except Exception as exc:
                logger.warning("CareerValidationService: failed loading domain map (%s)", exc)
        return {}

    def validate_career_title(self, career_name: str) -> bool:
        """
        Level 1 Universal Validation:
        Returns True if career_name represents a valid job title/profession.
        """
        if not career_name or not isinstance(career_name, str):
            return False

        clean_name = " ".join(career_name.split()).strip()
        if len(clean_name) < 4:
            return False

        name_lower = clean_name.lower()

        # Rejection Rule 1: Standalone technology / raw skill name
        if name_lower in self.rejected_tech:
            logger.info("CareerValidationService: REJECTED %r — raw technology name", clean_name)
            return False

        # Rejection Rule 2: Phrase indicator rejection
        for indicator in self.rejected_phrases:
            if indicator in name_lower:
                logger.info("CareerValidationService: REJECTED %r — contains non-job phrase indicator %r", clean_name, indicator)
                return False

        # Rejection Rule 3: Must contain at least one valid role noun/token
        words = set(re.findall(r'\w+', name_lower))
        if not (words & self.role_nouns):
            logger.info("CareerValidationService: REJECTED %r — missing valid role noun", clean_name)
            return False

        return True

    def is_relevant_for_student(self, career_name: str, student: "StudentProfile") -> bool:
        """
        Level 2 Student Relevance Validation:
        Checks if the career domain is aligned with the student's branch/degree using domain_mapping.json.
        """
        if not student or not student.branch:
            return True

        sb_lower = student.branch.strip().lower()
        career_lower = career_name.strip().lower()

        # Find student allowed keywords from domain_map
        allowed_keywords: set[str] = set()
        for branch_key, keywords in self.domain_map.items():
            if branch_key in sb_lower or any(word in sb_lower for word in branch_key.split()):
                allowed_keywords.update(keywords)

        if not allowed_keywords:
            return True  # Unconstrained branch

        # Check cross-domain hard rejections (e.g. CS student getting Agri role)
        if any(kw in sb_lower for kw in ("computer", "cs", "cse", "it", "software")):
            if any(agri_kw in career_lower for agri_kw in ("hydroponic", "greenhouse", "agronomist", "gardener", "farming")):
                logger.info("CareerValidationService: REJECTED %r for CS student branch %r", career_name, student.branch)
                return False

        return True

    def is_valid(self, career_name: str, student: "StudentProfile" | None = None) -> bool:
        """
        Master validation entry point.
        Checks Level 1 universal title validity, and if student is provided,
        checks Level 2 domain relevance.
        """
        if not self.validate_career_title(career_name):
            return False

        if student is not None:
            if not self.is_relevant_for_student(career_name, student):
                return False

        return True
