"""
Schemas for JobDescriptionAgent.

RoleProfile is the job-description equivalent of career_trend's
MergedCareerProfile: it's the structured unit that gets embedded,
stored in Qdrant, and retrieved on future cache hits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class JobDescriptionRequest:
    """Input to JobDescriptionAgent.run()."""
    role: str                                          # e.g. "Software Developer"
    seniority: Optional[str] = None                    # "Junior" | "Mid" | "Senior" | ...
    department: Optional[str] = None                   # e.g. "Engineering"
    company_name: Optional[str] = None
    company_summary: Optional[str] = None               # short blurb: culture, mission
    location: Optional[str] = None
    employment_type: Optional[str] = None                # "Full-time", "Contract", ...
    must_have_skills: list[str] = field(default_factory=list)   # user overrides, always included
    nice_to_have_skills: list[str] = field(default_factory=list)


@dataclass
class RoleProfile:
    """
    Structured knowledge unit for a role. Persisted to Qdrant (vector +
    payload) so the next request for the same role/seniority is a cache hit
    and skips Tavily + extraction entirely.
    """
    role_name: str
    category: str = "General"
    seniority: str = "Mid"
    summary: str = ""
    responsibilities: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    qualifications: list[str] = field(default_factory=list)
    tools_and_tech: list[str] = field(default_factory=list)
    similarity: float = 0.0            # populated by JDKnowledgeRetriever on read
    source: str = "knowledge"          # "knowledge" | "web"


@dataclass
class JobDescriptionResponse:
    title: str
    summary: str
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    qualifications: list[str]
    employment_type: Optional[str] = None
    location: Optional[str] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    metrics: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        meta = " · ".join(x for x in [self.location, self.employment_type] if x)
        if meta:
            lines += [meta, ""]
        lines += [self.summary, "", "## Responsibilities"]
        lines += [f"- {r}" for r in self.responsibilities]
        lines += ["", "## Required Skills"]
        lines += [f"- {s}" for s in self.required_skills]
        if self.preferred_skills:
            lines += ["", "## Preferred Skills"]
            lines += [f"- {s}" for s in self.preferred_skills]
        if self.qualifications:
            lines += ["", "## Qualifications"]
            lines += [f"- {q}" for q in self.qualifications]
        return "\n".join(lines)