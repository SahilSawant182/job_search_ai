# -*- coding: utf-8 -*-
from dataclasses import dataclass

STAGE_TO_YEARS = {
    "Immediate Placement": "3,4",
    "Growing":             "2,3,4",
    "Future":              "1,2,3",
}

SKILL_TIER_REQUIRED_THRESHOLD = 0.60
SKILL_TIER_PREFERRED_THRESHOLD = 0.30


@dataclass(frozen=True)
class RetrievalWeights:
    VECTOR = 0.35
    ACADEMIC = 0.10
    SKILL = 0.15
    INTEREST = 0.15
    YEAR = 0.10
    COUNTRY = 0.05
    QUALITY = 0.05
    FRESH = 0.05


JOB_SEARCH_DOMAINS = [
    "site:linkedin.com/jobs",
    "site:indeed.com",
    "site:naukri.com",
]

SALARY_SEARCH_DOMAINS = [
    "site:levels.fyi",
    "site:glassdoor.com",
    "site:payscale.com",
]
