# -*- coding: utf-8 -*-
from dataclasses import dataclass

STAGE_TO_YEARS = {
    "Immediate Placement": "3,4",
    "Growing":             "2,3,4",
    "Future":              "1,2,3",
}

SKILL_TIER_REQUIRED_THRESHOLD  = 0.60
SKILL_TIER_PREFERRED_THRESHOLD = 0.30


@dataclass(frozen=True)
class RetrievalWeights:
    """
    Hybrid scoring weights used by KnowledgeRetriever.
    Prioritizes interest and skill matches at 50% each.
    """
    VECTOR   = 0.00
    INTEREST = 0.50
    SKILL    = 0.50
    ACADEMIC = 0.00
    YEAR     = 0.00
    COUNTRY  = 0.00
    QUALITY  = 0.00


# Recommendation Engine scoring weights (must sum to 1.0)
RECOMMENDATION_WEIGHTS = {
    "skill_match":      0.50,
    "interest_match":   0.50,
    "keyword_match":    0.00,
    "degree_match":     0.00,
    "branch_match":     0.00,
    "year_suitability": 0.00,
}
# Configurable penalty weight applied when critical required skills are missing
CRITICAL_SKILL_PENALTY_WEIGHT = 0.15

MIN_FINAL_SCORE = 0.20


YEAR_STAGE_POLICY = {
    4: {"Immediate Placement": 1.0, "Growing": 0.5, "Future": 0.0},
    1: {"Future": 1.0, "Growing": 0.7, "Immediate Placement": 0.4},
    2: {"Growing": 1.0, "Immediate Placement": 0.7, "Future": 0.5},
    3: {"Growing": 1.0, "Immediate Placement": 0.7, "Future": 0.5},
}


JOB_SEARCH_DOMAINS = [
    "site:linkedin.com/jobs",
    "site:indeed.com",
    "site:naukri.com",
]
