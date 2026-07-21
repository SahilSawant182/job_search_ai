# -*- coding: utf-8 -*-
"""
InputNormalizer — config-driven shorthand expansion for StudentProfile.

Expands shortcuts like 'MERN', 'AI', 'Java', 'HVAC' into expanded skills
and keywords without hardcoding rules directly in Python code.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from job_search_ai.agents.career_trend.schemas import StudentProfile

logger = logging.getLogger(__name__)

_DEFAULT_MAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "normalization_map.json",
)


class InputNormalizer:
    """
    Normalizes a StudentProfile by expanding interests and skills
    based on the JSON configuration map.
    """

    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = config_path or _DEFAULT_MAP_PATH
        self.norm_map: dict[str, list[str]] = self._load_map()

    def _load_map(self) -> dict[str, list[str]]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {k.lower().strip(): v for k, v in data.items()}
            except Exception as exc:
                logger.warning("InputNormalizer: failed to load %s: %s", self.config_path, exc)
        return {}

    def normalize(self, student: StudentProfile) -> StudentProfile:
        """
        Return a new normalized StudentProfile with expanded skills and domain interests.
        Original profile fields are preserved; expanded terms are appended without duplicates.
        """
        normalized_interests = [i.strip() for i in student.interests if i and i.strip()]
        normalized_skills = [s.strip() for s in student.skills if s and s.strip()]

        existing_interests_lower = {i.lower() for i in normalized_interests}
        existing_skills_lower = {s.lower() for s in normalized_skills}

        # Check interests and skills against normalization map
        all_inputs = list(normalized_interests) + list(normalized_skills)
        for item in all_inputs:
            item_lower = item.lower().strip()
            if item_lower in self.norm_map:
                val = self.norm_map[item_lower]
                if isinstance(val, dict):
                    add_interests = val.get("interests", [])
                    add_skills = val.get("skills", [])
                elif isinstance(val, list):
                    add_interests = []
                    add_skills = val
                else:
                    continue

                for term in add_interests:
                    if term.lower() not in existing_interests_lower:
                        existing_interests_lower.add(term.lower())
                        normalized_interests.append(term)

                for term in add_skills:
                    if term.lower() not in existing_skills_lower:
                        existing_skills_lower.add(term.lower())
                        normalized_skills.append(term)

        # Build clean updated profile
        return StudentProfile(
            degree=student.degree,
            branch=student.branch,
            year=student.year,
            country=student.country,
            interests=normalized_interests,
            skills=normalized_skills,
        )

    def extract_keywords(self, student: StudentProfile) -> list[str]:
        """
        Extract normalized keywords from student interests, skills, and branch.
        """
        keywords: set[str] = set()

        for interest in student.interests:
            for word in interest.lower().split():
                if len(word) > 2:
                    keywords.add(word)

        for skill in student.skills:
            skill_clean = skill.lower().strip()
            keywords.add(skill_clean)

        for branch_word in student.branch.lower().split():
            if len(branch_word) > 3 and branch_word not in ("engineering", "technology", "degree", "science"):
                keywords.add(branch_word)

        return list(keywords)
