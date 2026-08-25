from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional

@dataclass
class RoadmapRequest:
    """Input parameters for the RoadmapAgent."""
    student: str
    career: str
    skill_gap_report: Optional[dict] = None

@dataclass
class RoadmapMilestone:
    """Represents a single learning milestone in a student's personalized roadmap."""
    sequence: int
    title: str
    type: str  # Learn, Build, Assess, Apply, Connect
    skill: str
    skill_tier: str  # Foundation, Core Domain, Industry, Emerging
    duration_days: int
    objective: str
    project: str
    points: List[str] = field(default_factory=list)
    linked_resource_type: Optional[str] = None
    linked_resource: Optional[str] = None
    completion_criteria: List[str] = field(default_factory=list)
    learning_outcomes: List[str] = field(default_factory=list)
    supporting_skills: List[str] = field(default_factory=list)

@dataclass
class UncoveredSkill:
    """Represents a missing skill that was not covered in the current roadmap."""
    skill: str
    reason: str

@dataclass
class RoadmapProfile:
    """The full personalized learning path roadmap payload."""
    career: str
    readiness_score: float
    milestones: List[RoadmapMilestone] = field(default_factory=list)
    uncovered_skills: List[UncoveredSkill] = field(default_factory=list)
    message: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize this profile to a plain Python dict."""
        return asdict(self)

@dataclass
class RoadmapResult:
    """Result wrapper returned by RoadmapAgent, containing metrics and validation status."""
    roadmap: RoadmapProfile
    metrics: dict = field(default_factory=dict)
    validation_status: str = "Valid"
    error_message: Optional[str] = None
    raw_response: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert the result into a clean Python dictionary."""
        return asdict(self)
