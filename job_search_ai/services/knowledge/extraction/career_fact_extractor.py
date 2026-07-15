# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/career_fact_extractor.py

from __future__ import annotations

import logging
import re
import frappe
from job_search_ai.services.knowledge.extraction.career_canonicalizer import CareerCanonicalizer

from job_search_ai.services.knowledge.constants import STAGE_TO_YEARS

logger = logging.getLogger(__name__)

_SALARY_RE = re.compile(
    r'(?:salary|package|ctc|lpa|lakh|pay|compensation)\D{0,20}'
    r'(?P<min>[\d,]+(?:\.\d+)?)\s*'
    r'(?:to|-|–|—)\s*(?P<max>[\d,]+(?:\.\d+)?)',
    re.IGNORECASE,
)
_SALARY_SINGLE_RE = re.compile(
    r'(?:salary|package|ctc|lpa|lakh|pay)\D{0,15}'
    r'(?P<amount>[\d,]+(?:\.\d+)?)',
    re.IGNORECASE,
)


class CareerFactExtractor:
    """
    Extracts structured career facts from cleaned text deterministically.
    No LLM calls. No network I/O. Pure Python heuristics.
    """

    @staticmethod
    def extract_list(
        cleaned_text: str,
        source_reliability: int,
        country: str,
        source_texts: list[str] | None = None,
        default_career_name: str | None = None,
    ) -> list[dict]:
        """
        Extract career facts. source_texts is a list of individual source page texts
        for per-source skill frequency counting. Falls back to [cleaned_text] if omitted.
        """
        if not cleaned_text or not cleaned_text.strip():
            return []

        sources = source_texts if source_texts else [cleaned_text]
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', cleaned_text) if p.strip()]

        raw_candidates = CareerFactExtractor._extract_career_titles(paragraphs)
        career_candidates = []
        for title in raw_candidates:
            if CareerCanonicalizer.is_marketing_title(title):
                continue
            canonical = CareerCanonicalizer.canonicalize(title)
            if canonical and canonical not in career_candidates:
                career_candidates.append(canonical)

        if not career_candidates:
            # Try to canonicalize default
            if default_career_name:
                canonical_def = CareerCanonicalizer.canonicalize(default_career_name)
                if canonical_def:
                    career_candidates = [canonical_def]

            if not career_candidates:
                logger.info("CareerFactExtractor: no valid career candidate extracted, rejecting document")
                return []

        full_text_lower = cleaned_text.lower()
        industry  = CareerFactExtractor._extract_industry(full_text_lower)
        category  = CareerFactExtractor._extract_category(full_text_lower)
        demand    = CareerFactExtractor._extract_demand(full_text_lower)
        stage     = CareerFactExtractor._extract_stage(full_text_lower)
        salaries  = CareerFactExtractor._extract_salary(full_text_lower, country)

        # Per-source skill extraction — returns {raw_token: source_count}
        skill_freq = CareerFactExtractor._extract_skills_per_source(sources)

        companies = CareerFactExtractor._extract_companies(cleaned_text)
        evidence_count = len(paragraphs)
        suitable_years = STAGE_TO_YEARS.get(stage or "Growing", "2,3,4")

        # Extract degrees and branches
        degrees_list, branches_list = CareerFactExtractor._extract_degrees_and_branches(full_text_lower)
        suitable_degrees = ", ".join(degrees_list)
        suitable_branches = ", ".join(branches_list)

        complete_fields = sum([bool(industry), bool(category), bool(demand), bool(skill_freq)])
        completeness = int((complete_fields / 4) * 100)
        confidence = min(100, int(source_reliability * 0.55 + completeness * 0.45))

        results = []
        for career_name in career_candidates[:3]:
            if not career_name or not career_name.strip():
                continue

            career_industry = CareerFactExtractor._extract_industry(
                career_name.lower() + " " + full_text_lower
            )
            if not career_industry or career_industry == "General":
                career_industry = industry

            career_category = CareerFactExtractor._extract_category(
                career_name.lower() + " " + full_text_lower
            )
            if not career_category or career_category == "Professional":
                career_category = category

            results.append({
                "career_name":    career_name.strip(),
                "industry":       career_industry or "General",
                "category":       career_category or "Professional",
                "demand":         demand or "Medium",
                "stage":          stage or "Growing",
                "summary":        "",
                "suitable_degrees": suitable_degrees,
                "suitable_branches": suitable_branches,
                "applicable_branches": suitable_branches,  # compat
                "suitable_years": suitable_years,
                "min_salary":     salaries.get("min"),
                "max_salary":     salaries.get("max"),
                "currency":       salaries.get("currency", "INR" if "india" in full_text_lower else "USD"),
                "skill_freq":     skill_freq,      # {raw_token: source_count} for SkillNormalizer
                "skills":         list(skill_freq.keys()),  # raw tokens for backward compat
                "companies":      companies,
                "evidence_count": max(1, evidence_count),
                "confidence":     confidence,
                "source_count":   len(sources),
                "source_reliability": source_reliability,
            })

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _canonicalize_career_name(raw: str) -> str:
        """Map a raw title candidate to a canonical career name using the CareerCanonicalizer."""
        return CareerCanonicalizer.canonicalize(raw) or raw

    @staticmethod
    def _extract_career_titles(paragraphs: list[str]) -> list[str]:
        candidates = []
        seen_lower: set[str] = set()

        _location_re = re.compile(
            r'^(hyderabad|bangalore|bengaluru|mumbai|delhi|pune|chennai|kolkata|'
            r'ahmedabad|noida|gurgaon|gurugram|india|usa|uk|dubai|singapore|'
            r'remote|work from home|wfh)\b',
            re.IGNORECASE,
        )
        _suffix_re = re.compile(
            r'\s*[—\-–|:]\s*(skills|career|guide|jobs|salary|2024|2025|2026|'
            r'trend|demand|scope|path|overview|top|best|review|report|hiring|'
            r'roadmap|comparison|vs\.?|versus|india).*$',
            re.IGNORECASE,
        )

        for para in paragraphs:
            first_line = para.split('\n')[0].strip()
            first_line = re.sub(r'^#{1,4}\s*', '', first_line).strip()
            first_line = _suffix_re.sub('', first_line).strip()

            if len(first_line) < 4 or len(first_line) > 60:
                continue
            if first_line.endswith(('.', ',', '?', '!')):
                continue
            if first_line and not first_line[0].isupper():
                continue
            if _location_re.match(first_line):
                continue
            if re.search(r'[—–‒\u2013\u2014]', first_line):
                continue

            # Check if there's at least one capitalized word of length >= 3
            words = first_line.split()
            if not any(w[0].isupper() and len(w) >= 3 for w in words):
                continue

            canonical = CareerFactExtractor._canonicalize_career_name(first_line)
            key = canonical.lower()
            if key not in seen_lower:
                seen_lower.add(key)
                candidates.append(canonical)

        return candidates

    @staticmethod
    def _extract_industry(text_lower: str) -> str:
        broad_industries = [
            "technology", "finance", "healthcare", "education", "manufacturing",
            "logistics", "retail", "consulting", "government", "media",
            "agriculture", "aerospace", "energy", "legal", "real estate", "hospitality"
        ]
        for ind in broad_industries:
            if re.search(r'\b' + re.escape(ind) + r'\b', text_lower):
                return ind.capitalize()
        return "General"

    @staticmethod
    def _extract_category(text_lower: str) -> str:
        broad_categories = [
            "developer", "engineer", "analyst", "scientist", "architect", "manager",
            "designer", "consultant", "specialist", "administrator", "officer",
            "advisor", "technician", "practitioner", "professional"
        ]
        for cat in broad_categories:
            if re.search(r'\b' + re.escape(cat) + r'\b', text_lower):
                return cat.capitalize()
        return "Professional"

    @staticmethod
    def _extract_demand(text_lower: str) -> str:
        if any(x in text_lower for x in ["explosive growth", "rapidly growing", "very high demand", "extremely high demand", "skyrocketing"]):
            return "Very High"
        if any(x in text_lower for x in ["high demand", "strong demand", "growing demand", "increasing demand", "significant demand"]):
            return "High"
        if any(x in text_lower for x in ["low demand", "declining", "shrinking"]):
            return "Low"

        high_signals = sum(1 for w in ["demand", "hiring", "opportunity", "grow", "expand"] if w in text_lower)
        if high_signals >= 3:
            return "High"
        return "Medium"

    @staticmethod
    def _extract_stage(text_lower: str) -> str:
        if any(x in text_lower for x in ["immediate", "entry level", "entry-level", "freshers", "junior", "placement"]):
            return "Immediate Placement"
        if any(x in text_lower for x in ["future", "next generation", "upcoming", "speculative", "research"]):
            return "Future"
        return "Growing"

    @staticmethod
    def _extract_skills_per_source(sources: list[str]) -> dict[str, int]:
        """
        Extract raw skill tokens per source and return {token: source_count}.
        Loads skill names and aliases dynamically from MariaDB.
        """
        token_source_counts: dict[str, int] = {}
        try:
            skills = frappe.get_all("Skill Master", filters={"active": 1}, fields=["skill_name"])
            aliases = frappe.get_all("Skill Alias", fields=["alias"])
            skill_words = set()
            for s in skills:
                val = s.get("skill_name")
                if val:
                    skill_words.add(val.strip().lower())
            for a in aliases:
                val = a.get("alias")
                if val:
                    skill_words.add(val.strip().lower())
        except Exception as e:
            logger.warning("Failed to fetch skills from database: %s", e)
            skill_words = set()

        if not skill_words:
            return {}

        sorted_words = sorted(list(skill_words), key=len, reverse=True)
        escaped_words = [re.escape(w) for w in sorted_words]
        pattern = re.compile(
            r'(?<![\w\+])(' + '|'.join(escaped_words) + r')(?![a-zA-Z\+])',
            re.IGNORECASE
        )

        for src_text in sources:
            found_in_this_source: set[str] = set()
            for m in pattern.finditer(src_text):
                tok = m.group(0).strip().lower()
                if tok:
                    found_in_this_source.add(tok)
            for tok in found_in_this_source:
                token_source_counts[tok] = token_source_counts.get(tok, 0) + 1
        return token_source_counts

    @staticmethod
    def _extract_salary(text_lower: str, country: str) -> dict:
        result: dict = {}
        m = _SALARY_RE.search(text_lower)
        if m:
            try:
                minsal = float(m.group("min").replace(",", ""))
                maxsal = float(m.group("max").replace(",", ""))
                if not (2020 <= minsal <= 2030 and 2020 <= maxsal <= 2030):
                    result["min"] = minsal
                    result["max"] = maxsal
            except (ValueError, AttributeError):
                pass
        if "min" not in result:
            m2 = _SALARY_SINGLE_RE.search(text_lower)
            if m2:
                try:
                    amount = float(m2.group("amount").replace(",", ""))
                    if not (2020 <= amount <= 2030):
                        result["min"] = amount
                except (ValueError, AttributeError):
                    pass
        if "inr" in text_lower or "lakh" in text_lower or "lpa" in text_lower or "india" in text_lower:
            result["currency"] = "INR"
        elif "usd" in text_lower or "dollar" in text_lower:
            result["currency"] = "USD"
        elif "gbp" in text_lower or "pound" in text_lower:
            result["currency"] = "GBP"
        elif country and "india" in country.lower():
            result["currency"] = "INR"
        else:
            result["currency"] = "USD"
        return result

    @staticmethod
    def _extract_companies(text: str) -> list[str]:
        found_companies = set()
        patterns = [
            r'\b(?:hiring|recruit|employ|work|jobs?|career?s?)\s+(?:at|by|in|with|for|include)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})',
            r'\b(?:employers|recruiters|companies)\s+(?:are|like|include)\s+([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})'
        ]
        for pat in patterns:
            for m in re.finditer(pat, text):
                comp = m.group(1).strip()
                comp_lower = comp.lower()
                if not any(w in comp_lower for w in ["the", "this", "our", "your", "hiring", "jobs", "career", "salary", "skills", "learn", "become"]):
                    from job_search_ai.services.knowledge.extraction.company_extractor import CompanyExtractor
                    cleaned = CompanyExtractor.extract_and_filter([comp])
                    if cleaned:
                        found_companies.add(cleaned[0])
        return sorted(list(found_companies))

    @staticmethod
    def _extract_degrees_and_branches(text_lower: str) -> tuple[list[str], list[str]]:
        degrees_found = set()
        degree_patterns = {
            "Engineering": r'\b(engineering|b\.?tech|b\.?e\.?|m\.?tech|m\.?e\.?)\b',
            "BCA": r'\bbca\b',
            "MCA": r'\bmca\b',
            "Science": r'\b(b\.?sc|m\.?sc|science)\b',
            "Business Administration": r'\b(bba|mba|business)\b',
            "Commerce": r'\bcommerce\b',
            "Law": r'\b(law|ll\.?b|ll\.?m)\b',
            "Medicine": r'\b(medicine|mbbs|md)\b',
            "Design": r'\bdesign\b',
            "Agriculture": r'\bagriculture\b',
        }
        for name, pat in degree_patterns.items():
            if re.search(pat, text_lower):
                degrees_found.add(name)
        branches_found = set()
        branch_patterns = [
            (r'\bcomputer (science|engineering)\b', "Computer Science"),
            (r'\bcs[e]?\b', "Computer Science"),
            (r'\binformation technology\b', "Information Technology"),
            (r'\bit\b', "Information Technology"),
            (r'\bsoftware engineering\b', "Software Engineering"),
            (r'\bdata science\b', "Data Science"),
            (r'\bmechanical\b', "Mechanical Engineering"),
            (r'\bcivil\b', "Civil Engineering"),
            (r'\belectrical\b', "Electrical Engineering"),
            (r'\belectronics\b', "Electronics Engineering"),
            (r'\bfinance\b', "Finance"),
            (r'\bmarketing\b', "Marketing"),
            (r'\bhuman resources?\b', "Human Resources"),
        ]
        for pat, name in branch_patterns:
            if re.search(pat, text_lower):
                branches_found.add(name)

        return sorted(list(degrees_found)), sorted(list(branches_found))
