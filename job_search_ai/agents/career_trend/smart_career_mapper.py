# -*- coding: utf-8 -*-
"""
SmartCareerMapper — Pure Python domain-aware career mapping.

Used as a deterministic fallback when vector knowledge base is empty
or returns no matches. It scores the student's profile against an
in-memory seed catalog of careers across all domains.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from job_search_ai.agents.career_trend.schemas import StudentProfile, CareerRecommendation

logger = logging.getLogger(__name__)

_DEFAULT_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "career_seed_catalog.json",
)

@dataclass
class ScoredSeedCareer:
    career_name: str
    category: str
    industry: str
    career_stage: str
    future_demand: str
    score: float
    matched_skills: list[str]
    required_skills: list[str]
    why_for_you: str


class SmartCareerMapper:
    """
    In-memory career scorer that finds the best match from a seed catalog.
    No LLM, <50ms execution.
    """
    _catalog: list[dict[str, Any]] = []

    def __init__(self, catalog_path: str = _DEFAULT_CATALOG_PATH):
        self.catalog_path = catalog_path
        if not SmartCareerMapper._catalog:
            self._load_catalog()

    def _load_catalog(self):
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                SmartCareerMapper._catalog = json.load(f)
            logger.info("SmartCareerMapper: loaded %d careers from catalog.", len(SmartCareerMapper._catalog))
        except Exception as exc:
            logger.error("SmartCareerMapper: failed to load catalog from %s: %s", self.catalog_path, exc)
            SmartCareerMapper._catalog = []

    def _clean_text(self, text: str) -> set[str]:
        """Normalize and tokenize text into words for fuzzy matching."""
        clean = re.sub(r'[^a-z0-9\s]', '', text.lower().strip())
        return {w for w in clean.split() if len(w) > 2}

    def _jaccard(self, a: set, b: set) -> float:
        if not a and not b:
            return 0.0
        if not a or not b:
            return 0.0
        
        matches = 0
        for item_a in a:
            for item_b in b:
                if item_a in item_b or item_b in item_a:
                    matches += 1
                    break
        return matches / max(len(a), len(b))

    def map_career(self, student: StudentProfile, top_k: int = 3) -> list[CareerRecommendation]:
        """
        Score all catalog careers against the student profile.
        Returns the top_k best matching CareerRecommendation objects.
        """
        if not self._catalog:
            return []

        student_skills = {s.lower().strip() for s in student.skills if s.strip()}
        student_interests = {i.lower().strip() for i in student.interests if i.strip()}
        student_branch_words = self._clean_text(student.branch)
        student_degree_words = self._clean_text(student.degree)

        scored_candidates: list[ScoredSeedCareer] = []

        for career in self._catalog:
            # 1. Skill Score
            req_skills = career.get("required_skills", [])
            pref_skills = career.get("preferred_skills", [])
            
            c_req_skills_set = {s.lower().strip() for s in req_skills}
            c_pref_skills_set = {s.lower().strip() for s in pref_skills}
            
            req_match = self._jaccard(student_skills, c_req_skills_set)
            pref_match = self._jaccard(student_skills, c_pref_skills_set)
            
            skill_score = (0.7 * req_match) + (0.3 * pref_match)

            matched_skill_names = [s for s in req_skills if s.lower().strip() in student_skills]
            if not matched_skill_names:
                # Fuzzy check
                for s in req_skills:
                    s_clean = s.lower().strip()
                    if any(s_clean in stu or stu in s_clean for stu in student_skills):
                        matched_skill_names.append(s)

            # 2. Interest Score
            interest_kws = {kw.lower().strip() for kw in career.get("interest_keywords", [])}
            interest_score = self._jaccard(student_interests, interest_kws)

            # 3. Domain Score (Branch + Degree)
            branch_score = 0.0
            for b in career.get("suitable_branches", []):
                b_words = self._clean_text(b)
                if self._jaccard(student_branch_words, b_words) > 0.4:
                    branch_score = 1.0
                    break
            
            degree_score = 0.0
            for d in career.get("suitable_degrees", []):
                d_words = self._clean_text(d)
                if self._jaccard(student_degree_words, d_words) > 0.4:
                    degree_score = 1.0
                    break
            
            domain_score = (branch_score * 0.7) + (degree_score * 0.3)

            # Final Score
            # If domain score is 0, strongly penalize unless skills/interests are incredibly high
            final_score = (skill_score * 0.45) + (interest_score * 0.35) + (domain_score * 0.20)
            
            if domain_score == 0.0 and final_score < 0.35:
                # Completely wrong domain and no strong skill/interest overlap
                continue

            # Build why_for_you
            if matched_skill_names:
                why = f"Your skills in {', '.join(matched_skill_names[:3])} strongly align with the requirements for this role."
            elif interest_score > 0:
                why = f"This path strongly aligns with your stated interests and academic background in {student.branch}."
            else:
                why = f"A complementary career path for {student.degree} ({student.branch}) students."

            scored_candidates.append(
                ScoredSeedCareer(
                    career_name=career["career_name"],
                    category=career["category"],
                    industry=career["industry"],
                    career_stage=career["career_stage"],
                    future_demand=career["future_demand"],
                    score=final_score,
                    matched_skills=matched_skill_names,
                    required_skills=req_skills,
                    why_for_you=why
                )
            )

        # Sort and take top K
        scored_candidates.sort(key=lambda x: x.score, reverse=True)
        
        # If top score is very low, let the LLM handle it (novel niche profile)
        if scored_candidates and scored_candidates[0].score < 0.15:
            logger.info("SmartCareerMapper: top score %.2f too low. Yielding to LLM for novel profile.", scored_candidates[0].score)
            return []

        results = []
        for cand in scored_candidates[:top_k]:
            conf = int(min(85, max(40, cand.score * 100)))
            
            # Ensure at least some skills are returned
            final_skills = list(cand.required_skills)
            for s in student.skills:
                if s not in final_skills and len(final_skills) < 8:
                    final_skills.append(s)

            results.append(
                CareerRecommendation(
                    career=cand.career_name,
                    category=cand.category,
                    industry=cand.industry,
                    career_stage=cand.career_stage,
                    future_demand=cand.future_demand,
                    confidence=conf,
                    why_for_you=cand.why_for_you,
                    skills=final_skills
                )
            )

        return results
