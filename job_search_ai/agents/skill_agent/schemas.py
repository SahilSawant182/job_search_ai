from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SkillRequest:
    """Input to SkillAgent.run()."""
    role: str                          # e.g. "Software Developer" — the job_profile value
    seniority: Optional[str] = None    # optional hint, doesn't change the doctype schema


@dataclass
class SkillProfile:
    """
    The cached/generated unit: structured skill profile for a role.
    This is what gets embedded and stored in Qdrant.
    """
    role_name: str
    foundation_skills: list[str] = field(default_factory=list)
    core_domain_skills: list[str] = field(default_factory=list)
    industry_skills: list[str] = field(default_factory=list)
    emerging_skills: list[str] = field(default_factory=list)
    similarity: float = 0.0        # populated on cache read
    source: str = "cache"          # "cache" | "llm"
    truncated_skills: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        seen_keys = set()
        tiers = ("foundation_skills", "core_domain_skills", "industry_skills", "emerging_skills")
        for tier_name in tiers:
            lst = getattr(self, tier_name) or []
            deduped = []
            for s in lst:
                if not s or not isinstance(s, str):
                    continue
                # Normalize key
                key = s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
                if key not in seen_keys:
                    seen_keys.add(key)
                    deduped.append(s.strip())
            setattr(self, tier_name, deduped)


@dataclass
class SkillResult:
    profile: SkillProfile
    doc_name: Optional[str] = None     # set if saved into the "Job Description" doctype
    metrics: dict = field(default_factory=dict)