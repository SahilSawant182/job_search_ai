"""
Schemas and Data Structures for Skill Gap Analyzer Service.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class StudentSkillItem:
    """Represents a verified skill item belonging to a student."""
    skill: str
    current_level: str = "Intermediate"  # Beginner, Intermediate, Advanced, Expert


@dataclass
class SkillGapRequest:
    """Request payload for skill gap analysis."""
    student: str
    role: Optional[str] = None
    job_description: Optional[str] = None
    readiness_threshold: float = 70.0


@dataclass
class SkillGapReport:
    """
    Structured report returned by the Skill Gap Analyzer Service.
    Directly compatible with upcoming Roadmap Agent.
    """
    student: str
    career: str
    matched_skills: List[str] = field(default_factory=list)
    missing_primary: List[str] = field(default_factory=list)
    missing_advanced: List[str] = field(default_factory=list)
    missing_expert: List[str] = field(default_factory=list)
    verified_skill_count: int = 0
    required_skill_count: int = 0
    matched_skill_count: int = 0
    missing_skill_count: int = 0
    readiness_score: float = 0.0
    ready_for_job: bool = False
    priority_order: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert report dataclass to dictionary."""
        return asdict(self)
