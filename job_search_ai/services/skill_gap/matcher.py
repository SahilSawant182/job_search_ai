"""
Semantic skill matching layer.

This module prepares canonical skill names before the deterministic
SkillGapAnalyzer compares lists and computes readiness.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from job_search_ai.services.skill_gap.normalizer import get_skill_key, normalize_skill
from job_search_ai.services.skill_gap.schemas import StudentSkillItem
from job_search_ai.services.skill_gap.skill_embedding_index import (
    SkillEmbeddingResolver,
    SkillResolution,
)

logger = logging.getLogger(__name__)

EmbeddingProvider = Callable[[str], List[float]]
LLMEquivalenceDecider = Callable[[str, str], bool]


SEMANTIC_ACRONYMS: Dict[str, str] = {
    "ai": "artificial intelligence",
    "api": "application programming interface",
    "aws": "amazon web services",
    "css": "cascading style sheets",
    "db": "database",
    "gcp": "google cloud platform",
    "html": "hypertext markup language",
    "js": "javascript",
    "ml": "machine learning",
    "nlp": "natural language processing",
    "ui": "user interface",
    "ux": "user experience",
}

SEMANTIC_STOP_WORDS = {
    "advanced",
    "basic",
    "basics",
    "beginner",
    "core",
    "development",
    "essential",
    "essentials",
    "framework",
    "fundamental",
    "fundamentals",
    "intermediate",
    "language",
    "programming",
    "technology",
    "tool",
    "tools",
}

FRAMEWORK_JS_SUFFIXES = {"angular", "next", "react", "vue"}
JAVASCRIPT_VERSION_TOKENS = {"ecmascript", "es"}


@dataclass(frozen=True)
class SkillMatch:
    """Represents a matcher decision for one student/required skill pair."""

    student_skill: str
    required_skill: str
    canonical_skill: str
    stage: str
    score: float = 1.0


@dataclass(frozen=True)
class CanonicalSkillInputs:
    """Canonicalized inputs passed into the deterministic analyzer."""

    student_skills: List[StudentSkillItem]
    primary_skills: List[str]
    advanced_skills: List[str]
    expert_skills: List[str]
    matches: List[SkillMatch]


class SemanticSkillMatcher:
    """
    Canonicalize skill lists with a staged matching pipeline.

    Stage order:
    1. Existing normalization.
    2. Exact normalized-key match.
    3. Semantic similarity using deterministic fingerprints, then embeddings.
    4. Optional LLM fallback for inconclusive pairs.
    """

    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
        llm_decider: Optional[LLMEquivalenceDecider] = None,
        skill_resolver: Optional[SkillEmbeddingResolver] = None,
        embedding_match_threshold: float = 0.86,
        embedding_inconclusive_threshold: float = 0.72,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.llm_decider = llm_decider
        self.skill_resolver = skill_resolver
        self.embedding_match_threshold = embedding_match_threshold
        self.embedding_inconclusive_threshold = embedding_inconclusive_threshold
        self._embedding_cache: Dict[str, List[float]] = {}
        self._resolution_cache: Dict[str, SkillResolution] = {}

    def canonicalize_inputs(
        self,
        student_skills: Sequence[StudentSkillItem],
        primary_skills: Sequence[str],
        advanced_skills: Sequence[str],
        expert_skills: Sequence[str],
    ) -> CanonicalSkillInputs:
        """Return canonical skill lists ready for deterministic comparison."""
        required_skills = self._dedupe_skills([*primary_skills, *advanced_skills, *expert_skills])
        student_canonical = self._canonicalize_student_skills(student_skills)
        expanded_student_skills = self._expand_student_skills(student_canonical)
        matches = self.match_skills([item.skill for item in expanded_student_skills], required_skills)
        canonical_by_required_key = {
            get_skill_key(match.required_skill): match.canonical_skill
            for match in matches
        }

        canonical_students = self._apply_student_match_canonicals(expanded_student_skills, matches)

        return CanonicalSkillInputs(
            student_skills=canonical_students,
            primary_skills=self._canonicalize_required_list(primary_skills, canonical_by_required_key),
            advanced_skills=self._canonicalize_required_list(advanced_skills, canonical_by_required_key),
            expert_skills=self._canonicalize_required_list(expert_skills, canonical_by_required_key),
            matches=matches,
        )

    def match_skills(
        self,
        student_skills: Sequence[str],
        required_skills: Sequence[str],
    ) -> List[SkillMatch]:
        """Match student skills to required skills without changing analyzer logic."""
        matches: List[SkillMatch] = []
        used_student_keys: set[str] = set()

        normalized_students = [normalize_skill(skill) for skill in student_skills if skill]
        normalized_required = [normalize_skill(skill) for skill in required_skills if skill]

        for required_skill in normalized_required:
            required_key = get_skill_key(required_skill)
            if not required_key:
                continue

            match = self._find_exact_match(required_skill, normalized_students, used_student_keys)
            if match is None:
                match = self._find_semantic_match(required_skill, normalized_students, used_student_keys)
            if match is None and self.skill_resolver is None:
                match = self._find_llm_match(required_skill, normalized_students, used_student_keys)

            if match is not None:
                used_student_keys.add(get_skill_key(match.student_skill))
                matches.append(match)

        return matches

    def _expand_student_skills(
        self, student_skills: List[StudentSkillItem]
    ) -> List[StudentSkillItem]:
        """Expand student skills through relationship graph, preserving highest proficiency levels."""
        try:
            from job_search_ai.services.skill_gap.relationship import expand_skill_relations
        except ImportError:
            return student_skills

        level_map = {}
        for item in student_skills:
            implied_skills = expand_skill_relations(item.skill)
            for implied in implied_skills:
                key = get_skill_key(implied)
                if not key:
                    continue
                # compare levels: Expert > Advanced > Intermediate > Beginner
                level_hierarchy = {"Beginner": 1, "Intermediate": 2, "Advanced": 3, "Expert": 4}
                current_lvl = item.current_level or "Intermediate"
                
                if key not in level_map:
                    level_map[key] = (implied, current_lvl)
                else:
                    existing_lvl = level_map[key][1]
                    if level_hierarchy.get(current_lvl, 2) > level_hierarchy.get(existing_lvl, 2):
                        level_map[key] = (implied, current_lvl)

        return [
            StudentSkillItem(skill=name, current_level=lvl)
            for name, lvl in level_map.values()
        ]

    def _canonicalize_student_skills(
        self, student_skills: Sequence[StudentSkillItem]
    ) -> List[StudentSkillItem]:
        seen_keys: set[str] = set()
        result: List[StudentSkillItem] = []

        for item in student_skills:
            canonical = normalize_skill(item.skill)
            
            # Semantic Resolution of Student Skill
            if self.skill_resolver is not None:
                try:
                    res = self._resolve_skill(canonical)
                    if res and (res.canonical_skill or res.normalized_skill):
                        canonical = res.canonical_skill or res.normalized_skill
                except Exception:
                    pass

            key = get_skill_key(canonical)
            if key and key not in seen_keys:
                seen_keys.add(key)
                result.append(
                    StudentSkillItem(
                        skill=canonical,
                        current_level=item.current_level or "Intermediate",
                    )
                )

        return result

    def _apply_student_match_canonicals(
        self,
        student_skills: Sequence[StudentSkillItem],
        matches: Sequence[SkillMatch],
    ) -> List[StudentSkillItem]:
        canonical_by_student_key = {
            get_skill_key(match.student_skill): match.canonical_skill
            for match in matches
        }
        seen_keys: set[str] = set()
        result: List[StudentSkillItem] = []

        for item in student_skills:
            canonical = canonical_by_student_key.get(get_skill_key(item.skill), item.skill)
            key = get_skill_key(canonical)
            if key and key not in seen_keys:
                seen_keys.add(key)
                result.append(
                    StudentSkillItem(
                        skill=canonical,
                        current_level=item.current_level or "Intermediate",
                    )
                )

        return result

    def _canonicalize_required_list(
        self,
        skills: Sequence[str],
        canonical_by_required_key: Dict[str, str],
    ) -> List[str]:
        seen_keys: set[str] = set()
        result: List[str] = []

        for skill in skills:
            canonical = canonical_by_required_key.get(get_skill_key(skill), normalize_skill(skill))
            key = get_skill_key(canonical)
            if key and key not in seen_keys:
                seen_keys.add(key)
                result.append(canonical)

        return result

    def _find_exact_match(
        self,
        required_skill: str,
        student_skills: Sequence[str],
        used_student_keys: set[str],
    ) -> Optional[SkillMatch]:
        required_key = get_skill_key(required_skill)
        for student_skill in student_skills:
            student_key = get_skill_key(student_skill)
            if student_key in used_student_keys:
                continue
            if student_key == required_key:
                return SkillMatch(
                    student_skill=student_skill,
                    required_skill=required_skill,
                    canonical_skill=required_skill,
                    stage="exact",
                )
        return None

    def _find_semantic_match(
        self,
        required_skill: str,
        student_skills: Sequence[str],
        used_student_keys: set[str],
    ) -> Optional[SkillMatch]:
        best: Optional[SkillMatch] = None

        for student_skill in student_skills:
            student_key = get_skill_key(student_skill)
            if student_key in used_student_keys:
                continue

            fingerprint_score = self._fingerprint_similarity(student_skill, required_skill)
            if fingerprint_score >= 1.0:
                return SkillMatch(
                    student_skill=student_skill,
                    required_skill=required_skill,
                    canonical_skill=required_skill,
                    stage="semantic_fingerprint",
                    score=fingerprint_score,
                )

            if self.skill_resolver is not None:
                index_match = self._find_index_match(student_skill, required_skill)
                if index_match is not None:
                    if best is None or index_match.score > best.score:
                        best = index_match
                continue

            embedding_score = self._embedding_similarity(student_skill, required_skill)
            if embedding_score >= self.embedding_match_threshold:
                candidate = SkillMatch(
                    student_skill=student_skill,
                    required_skill=required_skill,
                    canonical_skill=required_skill,
                    stage="semantic_embedding",
                    score=embedding_score,
                )
                if best is None or candidate.score > best.score:
                    best = candidate

        return best

    def _find_index_match(self, student_skill: str, required_skill: str) -> Optional[SkillMatch]:
        student_resolution = self._resolve_skill(student_skill)
        required_resolution = self._resolve_skill(required_skill)

        student_canonical = student_resolution.canonical_skill or student_resolution.normalized_skill
        required_canonical = required_resolution.canonical_skill or required_resolution.normalized_skill
        if get_skill_key(student_canonical) != get_skill_key(required_canonical):
            logger.info(
                "SemanticSkillMatcher: stage=qdrant_no_match student=%r required=%r student_resolution=%s required_resolution=%s",
                student_skill,
                required_skill,
                student_resolution.stage,
                required_resolution.stage,
            )
            return None

        score = min(
            student_resolution.score or 1.0,
            required_resolution.score or 1.0,
        )
        logger.info(
            "SemanticSkillMatcher: stage=qdrant_match student=%r required=%r canonical=%r score=%.4f",
            student_skill,
            required_skill,
            required_canonical,
            score,
        )
        return SkillMatch(
            student_skill=student_skill,
            required_skill=required_skill,
            canonical_skill=required_canonical,
            stage="semantic_index",
            score=score,
        )

    def _resolve_skill(self, skill: str) -> SkillResolution:
        key = get_skill_key(skill)
        if key not in self._resolution_cache:
            res = self.skill_resolver.resolve(
                skill,
                llm_decider=self.llm_decider,
            )
            if not res.accepted:
                try:
                    import frappe
                    normalized_skill = normalize_skill(skill)
                    normalized_key = get_skill_key(normalized_skill)
                    if normalized_key and not frappe.db.exists("Unknown Skill", normalized_key):
                        frappe.enqueue(
                            "job_search_ai.services.skill_gap.knowledge_builder.learn_skill_async",
                            queue="default",
                            timeout=300,
                            is_async=True,
                            raw_skill=skill,
                            source="SkillGapService"
                        )
                except Exception as exc:
                    logger.warning("SemanticSkillMatcher: failed to enqueue SkillKnowledgeBuilder for %r: %s", skill, exc)
            self._resolution_cache[key] = res
        return self._resolution_cache[key]

    def _find_llm_match(
        self,
        required_skill: str,
        student_skills: Sequence[str],
        used_student_keys: set[str],
    ) -> Optional[SkillMatch]:
        if self.llm_decider is None:
            return None

        for student_skill in student_skills:
            student_key = get_skill_key(student_skill)
            if student_key in used_student_keys:
                continue
            if self._embedding_similarity(student_skill, required_skill) > self.embedding_inconclusive_threshold:
                try:
                    if self.llm_decider(student_skill, required_skill):
                        return SkillMatch(
                            student_skill=student_skill,
                            required_skill=required_skill,
                            canonical_skill=required_skill,
                            stage="llm_fallback",
                        )
                except Exception as exc:
                    logger.warning(
                        "SemanticSkillMatcher: LLM fallback failed for %r vs %r: %s",
                        student_skill,
                        required_skill,
                        exc,
                    )

        return None

    def _embedding_similarity(self, left: str, right: str) -> float:
        if self.embedding_provider is None:
            return 0.0
        try:
            left_vector = self._get_embedding(left)
            right_vector = self._get_embedding(right)
        except Exception as exc:
            logger.warning("SemanticSkillMatcher: embedding comparison failed: %s", exc)
            return 0.0
        return _cosine_similarity(left_vector, right_vector)

    def _get_embedding(self, skill: str) -> List[float]:
        key = get_skill_key(skill)
        if key not in self._embedding_cache:
            self._embedding_cache[key] = self.embedding_provider(skill)
        return self._embedding_cache[key]

    def _fingerprint_similarity(self, left: str, right: str) -> float:
        left_fp = _semantic_fingerprint(left)
        right_fp = _semantic_fingerprint(right)
        if not left_fp or not right_fp:
            return 0.0
        if left_fp == right_fp:
            return 1.0
        return 0.0

    def _dedupe_skills(self, skills: Iterable[str]) -> List[str]:
        seen_keys: set[str] = set()
        result: List[str] = []
        for skill in skills:
            key = get_skill_key(skill)
            if key and key not in seen_keys:
                seen_keys.add(key)
                result.append(skill)
        return result


def default_embedding_provider() -> Optional[EmbeddingProvider]:
    """Return the configured embedding provider, or None outside configured environments."""
    try:
        from job_search_ai.services.ai.embedding_service import EmbeddingService

        service = EmbeddingService()
        return service.embed
    except Exception as exc:
        logger.warning("SemanticSkillMatcher: embedding provider unavailable: %s", exc)
        return None


def _semantic_fingerprint(skill: str) -> Tuple[str, ...]:
    key = get_skill_key(skill)
    if not key:
        return ()

    key = key.replace("nodejs", "node js").replace("reactjs", "react js")
    key = re.sub(r"(?<=\D)(?=\d)|(?<=\d)(?=\D)", " ", key)
    raw_tokens = re.findall(r"[a-z0-9]+", key.lower())
    expanded_tokens: List[str] = []

    for token in raw_tokens:
        if token in SEMANTIC_ACRONYMS:
            expanded_tokens.extend(SEMANTIC_ACRONYMS[token].split())
        else:
            expanded_tokens.append(token)

    collapsed = " ".join(expanded_tokens)
    for acronym, expansion in SEMANTIC_ACRONYMS.items():
        collapsed = re.sub(rf"\b{re.escape(expansion)}\b", acronym, collapsed)

    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", collapsed)
        if token not in SEMANTIC_STOP_WORDS
    ]
    tokens = _remove_javascript_framework_suffix(tokens)
    tokens = _remove_javascript_version_suffix(tokens)
    return tuple(tokens)


def _remove_javascript_framework_suffix(tokens: List[str]) -> List[str]:
    if len(tokens) == 2 and tokens[0] in FRAMEWORK_JS_SUFFIXES and tokens[1] == "js":
        return [tokens[0]]
    return tokens


def _remove_javascript_version_suffix(tokens: List[str]) -> List[str]:
    if len(tokens) >= 2 and tokens[0] == "js":
        suffix = tokens[1:]
        if suffix[0] in JAVASCRIPT_VERSION_TOKENS or all(token.isdigit() for token in suffix):
            return ["js"]
    return tokens


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
