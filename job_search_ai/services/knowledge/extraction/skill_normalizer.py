# -*- coding: utf-8 -*-
import frappe
import re

class SkillNormalizer:
    """
    Normalizes candidate technical skills against the centralized Skill Master repository.
    Loads and caches master skills and aliases in memory to avoid repetitive DB queries.
    Computes metadata for each skill: frequency, evidence_count, and importance.
    """

    # In-memory caches
    _master_cache = {}  # lower_case_name -> Canonical Name
    _alias_cache = {}   # lower_case_alias -> Canonical Name
    _initialized = False

    @classmethod
    def initialize_cache(cls, force=False):
        """
        Loads all Skill Master and Skill Alias records into the class-level cache.
        """
        if cls._initialized and not force:
            return

        cls._master_cache = {}
        cls._alias_cache = {}

        # 1. Fetch all active skills
        masters = frappe.get_all("Skill Master", filters={"active": 1}, fields=["name", "skill_name"])
        for m in masters:
            cls._master_cache[m.skill_name.lower()] = m.skill_name

        # 2. Fetch all aliases
        aliases = frappe.get_all("Skill Alias", fields=["alias", "parent"])
        for a in aliases:
            cls._alias_cache[a.alias.lower()] = a.parent

        cls._initialized = True

    @classmethod
    def clear_cache(cls):
        cls._initialized = False
        cls._master_cache = {}
        cls._alias_cache = {}

    def __init__(self):
        # Ensure cache is initialized
        self.initialize_cache()

    def normalize_all(self, candidate_tokens: list, cleaned_sources_text: list) -> list:
        """
        Normalizes list of raw candidate tokens, deduplicates, and calculates importance metadata.
        Args:
            candidate_tokens: list of raw skill tokens (e.g. ["js", "ReactJS", "python"])
            cleaned_sources_text: list of cleaned texts, each representing a single source webpage
        Returns:
            list of dicts: [
                {
                    "skill_name": "React",
                    "importance": 0.85,
                    "frequency": 12,
                    "evidence_count": 3
                },
                ...
            ]
        """
        if not candidate_tokens:
            return []

        normalized_map = {}  # canonical_name -> candidate_tokens/aliases matched
        
        # 1. Map candidate tokens to canonical skills in Skill Master
        for tok in candidate_tokens:
            if not tok:
                continue
            tok_clean = tok.strip().lower()
            
            canonical_name = None
            if tok_clean in self._master_cache:
                canonical_name = self._master_cache[tok_clean]
            elif tok_clean in self._alias_cache:
                canonical_name = self._alias_cache[tok_clean]

            if canonical_name:
                if canonical_name not in normalized_map:
                    normalized_map[canonical_name] = set()
                normalized_map[canonical_name].add(tok_clean)

        if not normalized_map:
            return []

        # 2. Compute frequency and evidence count for matched skills in the text sources
        total_sources = len(cleaned_sources_text) or 1
        results = []
        max_freq = 0
        raw_results = []

        for canonical_name, matched_tokens in normalized_map.items():
            frequency = 0
            evidence_count = 0

            # Gather all variations of the skill name including canonical name and matched tokens
            variations = {canonical_name.lower()} | matched_tokens
            
            # Count occurrences in each source webpage
            for src_text in cleaned_sources_text:
                src_lower = src_text.lower()
                src_count = 0
                for var in variations:
                    # Count using word boundaries to avoid partial matches
                    pattern = r'\b' + re.escape(var) + r'\b'
                    src_count += len(re.findall(pattern, src_lower))

                if src_count > 0:
                    frequency += src_count
                    evidence_count += 1

            # Fallback if text search found nothing but the token was extracted
            if frequency == 0:
                frequency = 1
                evidence_count = 1

            if frequency > max_freq:
                max_freq = frequency

            raw_results.append({
                "skill_name": canonical_name,
                "frequency": frequency,
                "evidence_count": evidence_count
            })

        # 3. Calculate importance score and compile final list
        for item in raw_results:
            freq = item["frequency"]
            ev_count = item["evidence_count"]
            
            # Formula: 60% based on breadth (evidence_count), 40% based on density (frequency)
            importance = (ev_count / total_sources) * 0.6 + (freq / (max_freq or 1.0)) * 0.4
            importance = round(min(1.0, importance), 2)

            # Determine skill_type dynamically based on importance score
            if importance >= 0.70:
                skill_type = "Required"
            elif importance >= 0.40:
                skill_type = "Advanced"
            else:
                skill_type = "Nice To Have"

            results.append({
                "skill_name": item["skill_name"],
                "importance": importance,
                "frequency": freq,
                "evidence_count": ev_count,
                "skill_type": skill_type
            })

        # Sort by importance descending
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results
