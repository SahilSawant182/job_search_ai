"""
Skill Normalizer Module.

Uses project-wide normalization logic (Skill Master / Skill Alias DocTypes &
normalization_map.json config) plus robust atomic skill parsing, dangling word removal,
and alias canonicalization.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)

# Cache for dynamic database lookups
_MASTER_CACHE: Dict[str, str] = {}
_ALIAS_CACHE: Dict[str, str] = {}
_CONFIG_MAP_CACHE: Dict[str, str] = {}
_INITIALIZED: bool = False

# Static canonical alias dictionary for standard tech & AI industry terms
DEFAULT_CANONICAL_ALIASES: Dict[str, str] = {
    # Acronyms & Full Names
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "automl": "Automated Machine Learning",
    "automated machine learning": "Automated Machine Learning",
    "iot": "Internet of Things",
    "internet of things": "Internet of Things",
    "internet of things integration": "Internet of Things",
    "gcp": "Google Cloud Platform",
    "google cloud platform": "Google Cloud Platform",
    "aws": "Amazon Web Services",
    "amazon web services": "Amazon Web Services",
    
    # Complete concept resolutions
    "structures": "Data Structures",
    "supervised": "Supervised Learning",
    "unsupervised": "Unsupervised Learning",
    "statistics fundamentals": "Statistics",
    "deep learning basics": "Deep Learning",
    "machine learning fundamentals": "Machine Learning",

    # Language & Tool basics/fundamentals
    "python basics": "Python",
    "python fundamentals": "Python",
    "javascript fundamentals": "JavaScript",
    "javascript basics": "JavaScript",
    "html basics": "HTML",
    "css basics": "CSS",
    "pytorch fundamentals": "PyTorch",
    "pytorch basics": "PyTorch",
    "tensorflow fundamentals": "TensorFlow",
    "tensorflow basics": "TensorFlow",
    "keras for machine learning": "Keras",
    "github for": "GitHub",
    "git version control": "Git",
    "version control systems": "Git",
}

DANGLING_WORDS: Set[str] = {
    "and", "or", "for", "using", "with", "the", "in", "by", "on", "of", "to", "etc", "etc.", "eg", "e.g.", "ie", "i.e.", "n/a", "none"
}


def clean_dangling_words(text: str) -> str:
    """
    Remove leading and trailing filler words like 'and', 'for', 'using', 'with', 'etc.'
    Example: 'and DynamoDB' -> 'DynamoDB', 'GitHub for' -> 'GitHub'
    """
    if not text:
        return ""
    words = text.strip().split()
    while words and words[0].lower().strip(".") in DANGLING_WORDS:
        words.pop(0)
    while words and words[-1].lower().strip(".") in DANGLING_WORDS:
        words.pop()
    return " ".join(words)


def _get_config_map_path() -> str:
    """Path to the project-wide normalization_map.json."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config",
        "normalization_map.json",
    )


def initialize_normalization_cache(force: bool = False) -> None:
    """
    Initialize normalization cache from Frappe DB (Skill Master / Skill Alias)
    and normalization_map.json.
    """
    global _MASTER_CACHE, _ALIAS_CACHE, _CONFIG_MAP_CACHE, _INITIALIZED

    if _INITIALIZED and not force:
        return

    _MASTER_CACHE = {}
    _ALIAS_CACHE = {}
    _CONFIG_MAP_CACHE = {}

    # 1. Load static aliases into _ALIAS_CACHE
    for alias_key, canonical_name in DEFAULT_CANONICAL_ALIASES.items():
        _ALIAS_CACHE[alias_key] = canonical_name

    # 2. Load from normalization_map.json
    config_path = _get_config_map_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, val in data.items():
                    key_clean = key.lower().strip()
                    if isinstance(val, dict):   
                        skills = val.get("skills", [])
                        for s in skills:
                            k = s.lower().strip()
                            if s and any(c.isupper() for c in s):     
                                _CONFIG_MAP_CACHE[k] = s
                            elif k not in _CONFIG_MAP_CACHE:
                                _CONFIG_MAP_CACHE[k] = s.title()
                    elif isinstance(val, str):
                        _CONFIG_MAP_CACHE[key_clean] = val.title() if not any(c.isupper() for c in val) else val
        except Exception as exc:
            logger.warning("SkillNormalizer: failed to load %s: %s", config_path, exc)

    # 3. Load from Frappe DocTypes if Frappe DB is active
    try:
        import frappe
        if getattr(frappe, "db", None) and hasattr(frappe.db, "get_all"):
            masters = frappe.get_all("Skill Master", filters={"active": 1}, fields=["skill_name"])
            for m in masters:
                name_val = m.get("skill_name")
                if name_val:
                    _MASTER_CACHE[name_val.lower().strip()] = name_val

            aliases = frappe.get_all("Skill Alias", fields=["alias", "parent"])
            for a in aliases:
                alias_val = a.get("alias")
                parent_val = a.get("parent")
                if alias_val and parent_val:
                    _ALIAS_CACHE[alias_val.lower().strip()] = parent_val
    except Exception:
        # Running outside Frappe context
        pass

    _INITIALIZED = True


def invalidate_normalization_cache() -> None:
    """
    Force reload the normalization cache by clearing existing cache entries
    and resetting the initialized state.
    """
    initialize_normalization_cache(force=True)


def get_skill_key(skill_name: str) -> str:
    """
    Generate a normalized matching key for a skill string.
    """
    if not skill_name:
        return ""

    cleaned_raw = clean_dangling_words(skill_name).strip().lower()
    initialize_normalization_cache()

    # Alias cache resolution
    if cleaned_raw in _ALIAS_CACHE:
        cleaned_raw = _ALIAS_CACHE[cleaned_raw].lower().strip()

    # Clean non-alphanumeric characters
    cleaned = re.sub(r"[^\w\s]", "", cleaned_raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if cleaned in _ALIAS_CACHE:
        cleaned = _ALIAS_CACHE[cleaned].lower().strip()

    return cleaned or cleaned_raw


def normalize_skill(skill_name: str) -> str:
    """
    Return the single source of truth canonical display name for a skill.
    """
    if not skill_name or not skill_name.strip():
        return ""

    trimmed = clean_dangling_words(skill_name.strip())
    key = get_skill_key(trimmed)
    initialize_normalization_cache()

    # 1. Check Skill Master cache
    if key in _MASTER_CACHE:
        return _MASTER_CACHE[key]

    # 2. Check Skill Alias cache
    if key in _ALIAS_CACHE:
        alias_target = _ALIAS_CACHE[key]
        return _MASTER_CACHE.get(alias_target.lower().strip(), alias_target)

    # 3. Check static default aliases
    if key in DEFAULT_CANONICAL_ALIASES:
        return DEFAULT_CANONICAL_ALIASES[key]

    raw_lower = trimmed.lower()
    if raw_lower in DEFAULT_CANONICAL_ALIASES:
        return DEFAULT_CANONICAL_ALIASES[raw_lower]

    # 4. Check normalization_map.json (unless provided skill has custom capitalization)
    if any(c.isupper() for c in trimmed):
        return trimmed

    if key in _CONFIG_MAP_CACHE:
        return _CONFIG_MAP_CACHE[key]

    # 5. Fallback formatting
    if len(trimmed) <= 3 and "/" not in trimmed and "." not in trimmed:
        return trimmed.upper()
    
    return trimmed.title()


FLUFF_SUFFIXES: List[str] = [
    r"\bversion control\b",
    r"\bdata visualization tools\b",
    r"\bbig data technologies\b",
    r"\btechnologies\b",
    r"\btools\b",
]


def decompose_skill_token(token: str) -> List[str]:
    """
    Decompose a composite skill token into individual atomic skills.
    Splits conjunctions ('or', 'and', '/', ',', ';'), strips parenthetical groups,
    and removes dangling prepositions.
    """
    if not token or not token.strip():
        return []

    raw = clean_dangling_words(token.strip())
    parens = re.findall(r"\(([^)]+)\)", raw)
    main_text = re.sub(r"\([^)]+\)", "", raw).strip()

    pieces: List[str] = []
    if main_text:
        pieces.append(main_text)
    for paren in parens:
        pieces.append(paren)

    atomic_tokens: List[str] = []
    for piece in pieces:
        sub_splits = re.split(r"\s+or\s+|\s+and\s+|[/,;]", piece, flags=re.IGNORECASE)
        for sub in sub_splits:
            cleaned = clean_dangling_words(sub.strip())
            if not cleaned:
                continue

            stripped = cleaned
            for fluff_pat in FLUFF_SUFFIXES:
                new_stripped = re.sub(fluff_pat, "", stripped, flags=re.IGNORECASE).strip()
                if new_stripped and len(new_stripped) >= 2:
                    stripped = clean_dangling_words(new_stripped)

            if stripped:
                cleaned_lower = stripped.lower().strip(".")
                if cleaned_lower not in DANGLING_WORDS:
                    atomic_tokens.append(stripped)

    return atomic_tokens


def parse_skill_string(skills_input: Union[str, List[str], None]) -> List[str]:
    """
    Parse a skill string or list of skill strings into a deduplicated list of atomic canonical skills.
    Decomposes grouped descriptions (e.g. 'Git Version Control' -> ['Git']).
    """
    if not skills_input:
        return []

    raw_list: List[str] = []
    comma_outside_parens = re.compile(r',\s*(?![^()]*\))')

    if isinstance(skills_input, str):
        raw_list = [s.strip() for s in comma_outside_parens.split(skills_input) if s.strip()]
    elif isinstance(skills_input, list):
        for item in skills_input:
            if isinstance(item, str):
                raw_list.extend([s.strip() for s in comma_outside_parens.split(item) if s.strip()])

    seen_keys: Set[str] = set()
    result: List[str] = []

    for raw_skill in raw_list:
        atomic_pieces = decompose_skill_token(raw_skill)
        for piece in atomic_pieces:
            key = get_skill_key(piece)
            if key and key not in seen_keys:
                seen_keys.add(key)
                result.append(normalize_skill(piece))

    return result
