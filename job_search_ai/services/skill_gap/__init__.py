"""
Skill Gap Analyzer Package.

Pure Python deterministic service for student skill vs job description skill gap analysis.
Provides both Frappe-decoupled pure SkillGapAnalyzer and Frappe SkillGapService.
"""

from job_search_ai.services.skill_gap.analyzer import SkillGapAnalyzer
from job_search_ai.services.skill_gap.matcher import SemanticSkillMatcher
from job_search_ai.services.skill_gap.skill_embedding_index import (
    PersistentSkillEmbeddingCache,
    SkillEmbeddingBuilder,
    SkillEmbeddingIndex,
    SkillEmbeddingResolver,
    SkillIndexConfig,
)
from job_search_ai.services.skill_gap.normalizer import (
    get_skill_key,
    initialize_normalization_cache,
    normalize_skill,
    parse_skill_string,
)
from job_search_ai.services.skill_gap.schemas import (
    SkillGapReport,
    SkillGapRequest,
    StudentSkillItem,
)

__all__ = [
    "SkillGapService",
    "SkillGapAnalyzer",
    "SemanticSkillMatcher",
    "SkillEmbeddingResolver",
    "SkillEmbeddingBuilder",
    "SkillEmbeddingIndex",
    "PersistentSkillEmbeddingCache",
    "SkillIndexConfig",
    "SkillGapReport",
    "SkillGapRequest",
    "StudentSkillItem",
    "normalize_skill",
    "get_skill_key",
    "parse_skill_string",
    "initialize_normalization_cache",
]


def __getattr__(name: str):
    if name == "SkillGapService":
        from job_search_ai.services.skill_gap.service import SkillGapService

        return SkillGapService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
