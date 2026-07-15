# -*- coding: utf-8 -*-
import frappe
import re
from job_search_ai.services.knowledge.constants import (
    SKILL_TIER_REQUIRED_THRESHOLD,
    SKILL_TIER_PREFERRED_THRESHOLD,
)


class SkillNormalizer:
    """
    Normalizes candidate technical skills against the centralized Skill Master repository.
    """

    _master_cache = {}
    _alias_cache = {}
    _initialized = False

    @classmethod
    def initialize_cache(cls, force=False):
        if cls._initialized and not force:
            return
        cls._master_cache = {}
        cls._alias_cache = {}
        masters = frappe.get_all("Skill Master", filters={"active": 1}, fields=["name", "skill_name"])
        for m in masters:
            name_val = m.get("skill_name")
            if name_val:
                cls._master_cache[name_val.lower()] = name_val
        aliases = frappe.get_all("Skill Alias", fields=["alias", "parent"])
        for a in aliases:
            alias_val = a.get("alias")
            parent_val = a.get("parent")
            if alias_val and parent_val:
                cls._alias_cache[alias_val.lower()] = parent_val
        cls._initialized = True

    @classmethod
    def clear_cache(cls):
        cls._initialized = False
        cls._master_cache = {}
        cls._alias_cache = {}

    def __init__(self):
        self.initialize_cache()

    def normalize_all(
        self,
        candidate_tokens,
        cleaned_sources_text: list,
        skill_freq: dict | None = None,
    ) -> list:
        """
        Normalize raw skill tokens to canonical names and compute skill_type.

        Parameters
        ----------
        candidate_tokens     : list[str]  — raw tokens extracted from text
        cleaned_sources_text : list[str]  — individual source page texts
        skill_freq           : dict|None  — {raw_token: source_count} pre-computed
                               by CareerFactExtractor._extract_skills_per_source()

        skill_type — evidence proportion based.
        """
        if not candidate_tokens:
            return []

        total_sources = max(1, len(cleaned_sources_text))
        normalized_map: dict[str, dict] = {}

        for tok in candidate_tokens:
            if not tok:
                continue
            tok_clean = tok.strip().lower()
            canonical_name = (
                self._master_cache.get(tok_clean)
                or self._alias_cache.get(tok_clean)
                or tok.strip()
            )
            # Ensure proper capitalization if not in master cache
            if canonical_name.lower() == tok_clean:
                # Capitalize acronyms or normal tech words nicely
                if len(canonical_name) <= 3:
                    canonical_name = canonical_name.upper()
                else:
                    canonical_name = canonical_name.title()

            if canonical_name:
                if canonical_name not in normalized_map:
                    normalized_map[canonical_name] = {"tokens": set(), "source_count": 0, "frequency": 0}
                normalized_map[canonical_name]["tokens"].add(tok_clean)
                if skill_freq and tok_clean in skill_freq:
                    normalized_map[canonical_name]["source_count"] = max(
                        normalized_map[canonical_name]["source_count"],
                        skill_freq[tok_clean],
                    )

        if not normalized_map:
            return []

        max_freq = 0
        for canonical_name, data in normalized_map.items():
            variations = {canonical_name.lower()} | data["tokens"]
            total_freq = 0
            src_count_from_scan = 0
            for src_text in cleaned_sources_text:
                src_lower = src_text.lower()
                src_hits = sum(
                    len(re.findall(r'\b' + re.escape(v) + r'\b', src_lower))
                    for v in variations
                )
                if src_hits > 0:
                    src_count_from_scan += 1
                    total_freq += src_hits
            data["frequency"] = max(1, total_freq)
            if data["source_count"] == 0:
                data["source_count"] = max(1, src_count_from_scan)
            if data["frequency"] > max_freq:
                max_freq = data["frequency"]

        results = []
        for canonical_name, data in normalized_map.items():
            src_count = data["source_count"]
            freq = data["frequency"]
            evidence_proportion = src_count / total_sources

            if evidence_proportion >= SKILL_TIER_REQUIRED_THRESHOLD:
                skill_type = "Required"
            elif evidence_proportion >= SKILL_TIER_PREFERRED_THRESHOLD:
                skill_type = "Preferred"
            else:
                skill_type = "Nice To Have"

            importance = round(
                min(1.0, evidence_proportion * 0.7 + (freq / (max_freq or 1.0)) * 0.3),
                2,
            )
            results.append({
                "skill_name":     canonical_name,
                "importance":     importance,
                "frequency":      freq,
                "evidence_count": src_count,
                "skill_type":     skill_type,
            })

        results.sort(key=lambda x: x["importance"], reverse=True)
        return results
