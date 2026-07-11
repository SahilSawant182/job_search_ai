"""
StudentContextBuilder — builds deterministic student contexts for the CareerTrendAgent.

Responsibility:
    Compute deterministic business facts (placement readiness, graduation timeline,
    recommendation horizon, career goal) based on the student's academic year.
    No semantic career mapping. Fully degree-agnostic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from job_search_ai.agents.career_trend.schemas import StudentProfile

logger = logging.getLogger(__name__)


@dataclass
class StudentContext:
    """
    Holds the deterministic student context parameters.
    """
    degree: str
    branch: str
    academic_year: int
    country: str
    interests: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    placement_readiness: str = ""
    graduation_timeline: str = ""
    recommendation_horizon: str = ""
    career_goal: str = ""

    def to_dict(self) -> dict:
        return {
            "degree": self.degree,
            "branch": self.branch,
            "academic_year": self.academic_year,
            "country": self.country,
            "interests": self.interests,
            "skills": self.skills,
            "placement_readiness": self.placement_readiness,
            "graduation_timeline": self.graduation_timeline,
            "recommendation_horizon": self.recommendation_horizon,
            "career_goal": self.career_goal,
        }


class StudentContextBuilder:
    """
    Constructs a StudentContext from a StudentProfile by applying simple,
    deterministic business rules for any degree type.
    """

    def build(self, student: StudentProfile) -> StudentContext:
        logger.info("Building student context for year %d", student.year)

        # 1. Placement Readiness
        if student.year == 1:
            readiness = "Exploration"
        elif student.year == 2:
            readiness = "Foundation Building"
        elif student.year == 3:
            readiness = "Internship Preparation"
        elif student.year == 4:
            readiness = "Placement Ready"
        else:
            readiness = "Career Growth"

        # 2. Recommendation Horizon
        if student.year == 1:
            horizon = "Future (3–5 years)"
        elif student.year == 2:
            horizon = "Future (2–4 years)"
        elif student.year == 3:
            horizon = "Near Future (1–3 years)"
        else:
            horizon = "Immediate Placement (0–12 months)"

        # 3. Graduation Timeline
        if student.year == 1:
            timeline = "Graduating in approximately 3–4 years"
        elif student.year == 2:
            timeline = "Graduating in approximately 2–3 years"
        elif student.year == 3:
            timeline = "Graduating in approximately 1–2 years"
        else:
            timeline = "Graduating in less than 1 year (or already graduated)"

        # 4. Career Goal
        if student.year >= 4 or student.year <= 0:
            goal = "Immediate Placement / Job Search"
        elif student.year == 3:
            goal = "Internship and Skill Specialisation"
        else:
            goal = "Foundational Skill Building and Academic Exploration"

        return StudentContext(
            degree=student.degree,
            branch=student.branch,
            academic_year=student.year,
            country=student.country,
            interests=student.interests,
            skills=student.skills,
            placement_readiness=readiness,
            graduation_timeline=timeline,
            recommendation_horizon=horizon,
            career_goal=goal,
        )
