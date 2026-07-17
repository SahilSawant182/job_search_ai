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

    The vector similarity dominates (0.40) because Qdrant payloads now contain
    rich career metadata — the embedding is more semantically meaningful.
    Interest overlap is second most important signal (0.20).
    """
    VECTOR   = 0.40
    INTEREST = 0.20
    SKILL    = 0.15
    ACADEMIC = 0.10
    YEAR     = 0.10
    COUNTRY  = 0.03
    QUALITY  = 0.02


# Recommendation Engine scoring weights (must sum to 1.0)
RECOMMENDATION_WEIGHTS = {
    "skill_match":      0.40,
    "interest_match":   0.25,
    "year_suitability": 0.15,
    "degree_match":     0.10,
    "branch_match":     0.05,
    "market_demand":    0.05,
}


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
