"""
Shared dataclass schemas for the Career Trend Agent.

Design principles:
  - All data that crosses service boundaries is a typed dataclass.
  - No plain dicts are used between services.
  - Fields use sensible defaults so callers only need to supply what
    they know.

These schemas are intentionally framework-agnostic. They can be
serialized to JSON, stored in a database, passed to a Next.js frontend,
or handed off to another agent without modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class StudentProfile:
    """
    Describes a student whose career trajectory we are analysing.

    Attributes:
        degree:    Formal degree being pursued (e.g. "Engineering").
        branch:    Specialisation within the degree (e.g. "Computer Engineering").
        year:      Current year of study (1-indexed, e.g. 1 for first year).
        country:   Country of study / job market of interest.
        interests: Free-form list of topics the student is passionate about.
        skills:    Programming languages, tools, or frameworks already known.
    """

    degree: str
    branch: str
    year: int
    country: str
    interests: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.degree.strip():
            raise ValueError("StudentProfile.degree must not be empty.")
        if not self.branch.strip():
            raise ValueError("StudentProfile.branch must not be empty.")
        if self.year < 1:
            raise ValueError("StudentProfile.year must be a positive integer.")
        if not self.country.strip():
            raise ValueError("StudentProfile.country must not be empty.")


@dataclass
class SearchResult:
    """
    A single result returned by the search service.

    Attributes:
        title:   Page or article title.
        url:     Canonical URL of the source.
        content: Extracted body text (truncated to a useful summary length).
        source:  Human-readable source name (e.g. "LinkedIn", "WEF").
        score:   Tavily search relevance score.
    """

    title: str
    url: str
    content: str
    source: str
    score: float = 0.0

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("SearchResult.url must not be empty.")


@dataclass
class CareerRecommendation:
    """
    A single recommended career path for the student.

    Attributes:
        career:        Job title or role name (e.g. "AI Engineer").
        category:      Broad industry category (e.g. "Artificial Intelligence").
        confidence:    Agent's confidence score 0–100 (int).
        why_for_you:   Personalised explanation referencing the student's profile.
        career_stage:  Growth stage of this role: "Emerging", "Growing", or "Established".
        future_demand: Projected market demand: "Very High", "High", or "Moderate".
        industry:      Broad industry sector/domain (e.g. "Cybersecurity").
        skills:        Specific skills the student should acquire or highlight.
    """

    career: str
    category: str
    confidence: int
    why_for_you: str
    career_stage: str
    future_demand: str
    industry: str
    skills: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (0 <= self.confidence <= 100):
            raise ValueError(
                f"CareerRecommendation.confidence must be 0-100, got {self.confidence}."
            )
        if self.career_stage not in ("Emerging", "Growing", "Established"):
            raise ValueError(
                f"CareerRecommendation.career_stage must be 'Emerging', 'Growing', or 'Established', got {self.career_stage!r}."
            )
        if self.future_demand not in ("Very High", "High", "Moderate"):
            raise ValueError(
                f"CareerRecommendation.future_demand must be 'Very High', 'High', or 'Moderate', got {self.future_demand!r}."
            )


@dataclass
class CareerTrendResponse:
    """
    The final output delivered to the caller.

    Attributes:
        recommended_paths: Ordered list of career recommendations
                           (highest confidence first).
        strategy:          A short strategic paragraph summarising the
                           overall advice for the student.
        generated_at:      UTC timestamp of when the analysis was completed.
    """

    recommended_paths: list[CareerRecommendation]
    strategy: str
    generated_at: Optional[datetime] = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    def to_dict(self) -> dict:
        """
        Serialise this response to a plain dictionary suitable for JSON
        encoding, API responses, or database storage.
        """
        return {
            "generated_at": (
                self.generated_at.isoformat() if self.generated_at else None
            ),
            "strategy": self.strategy,
            "recommended_paths": [
                {
                    "career": r.career,
                    "category": r.category,
                    "confidence": r.confidence,
                    "why_for_you": r.why_for_you,
                    "career_stage": r.career_stage,
                    "future_demand": r.future_demand,
                    "industry": r.industry,
                    "skills": r.skills,
                }
                for r in self.recommended_paths
            ],
        }
