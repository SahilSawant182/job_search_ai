# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/career_fact_extractor.py

from __future__ import annotations

import logging
import re
import frappe
from job_search_ai.services.knowledge.extraction.career_canonicalizer import CareerCanonicalizer

from job_search_ai.services.knowledge.constants import STAGE_TO_YEARS

logger = logging.getLogger(__name__)

# Removed salary regexes as they are no longer needed for career recommendation template.


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
        demand    = CareerFactExtractor._extract_demand(full_text_lower)
        stage     = CareerFactExtractor._extract_stage(full_text_lower)

        # Per-source skill extraction — returns {raw_token: source_count}
        skill_freq = CareerFactExtractor._extract_skills_per_source(sources)

        evidence_count = len(paragraphs)
        suitable_years = STAGE_TO_YEARS.get(stage or "Growing", "2,3,4")

        # Extract degrees and branches
        degrees_list, branches_list = CareerFactExtractor._extract_degrees_and_branches(full_text_lower)
        suitable_degrees = ", ".join(degrees_list)
        suitable_branches = ", ".join(branches_list)

        complete_fields = sum([bool(demand), bool(skill_freq)])
        completeness = int((complete_fields / 2) * 100)
        confidence = min(100, int(source_reliability * 0.55 + completeness * 0.45))

        results = []
        for career_name in career_candidates[:3]:
            if not career_name or not career_name.strip():
                continue

            industry = CareerFactExtractor._extract_industry(career_name, full_text_lower)
            category = CareerFactExtractor._extract_category(career_name, full_text_lower)

            results.append({
                "career_name":    career_name.strip(),
                "industry":       industry,
                "category":       category,
                "demand":         demand or "Medium",
                "stage":          stage or "Growing",
                "summary":        "",
                "suitable_degrees": suitable_degrees,
                "suitable_branches": suitable_branches,
                "applicable_branches": suitable_branches,  # compat
                "suitable_years": suitable_years,
                "min_salary":     None,
                "max_salary":     None,
                "currency":       "",
                "skill_freq":     skill_freq,      # {raw_token: source_count} for SkillNormalizer
                "skills":         list(skill_freq.keys()),  # raw tokens for backward compat
                "companies":      [],
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
    def _extract_industry(career_name: str, text_lower: str) -> str:
        """
        Infer the industry from the career name and the full text.
        Priority: career name signal first (exact + substring), then text-level signals.
        Returns a clean, short industry string (2-4 words max).
        """
        name_l = career_name.strip().lower()

        # ── Exact single-word / acronym matches (highest priority) ──────
        _exact_ai      = {"ai", "ml", "llm", "nlp", "gpt"}
        _exact_cloud   = {"aws", "gcp", "azure", "devops", "sre", "devsecops"}
        _exact_data    = {"bi", "olap", "etl"}
        _exact_iot     = {"iot", "rtos", "plc", "scada"}
        _exact_cyber   = {"soc", "siem", "ciso"}
        _exact_finance = {"cfa", "ca", "actuary"}
        _exact_qa      = {"qa", "qe", "sdet"}

        if name_l in _exact_ai:
            return "Artificial Intelligence"
        if name_l in _exact_cloud:
            return "Cloud & DevOps"
        if name_l in _exact_data:
            return "Data & Analytics"
        if name_l in _exact_iot:
            return "Robotics & Automation"
        if name_l in _exact_cyber:
            return "Cybersecurity"
        if name_l in _exact_finance:
            return "Finance & Banking"
        if name_l in _exact_qa:
            return "Quality Assurance"

        # ── Substring matches on career name ─────────────────────────────
        if any(k in name_l for k in ["artificial intelligence", "machine learning", "deep learning",
                                      "computer vision", "generative ai", "gen ai",
                                      "ai engineer", "ml engineer", "ai developer"]):
            return "Artificial Intelligence"
        # Catch "... AI" suffix or "AI ..." prefix in multi-word titles
        if name_l.startswith("ai ") or name_l.endswith(" ai"):
            return "Artificial Intelligence"
        if any(k in name_l for k in ["data scientist", "data analyst", "data engineer",
                                      "analytics", "business intelligence"]):
            return "Data & Analytics"
        if any(k in name_l for k in ["cloud", "aws", "azure", "gcp", "devops",
                                      "site reliability", "infrastructure", "platform engineer"]):
            return "Cloud & DevOps"
        if any(k in name_l for k in ["cyber", "security", "penetration", "ethical hack",
                                      "soc analyst", "infosec"]):
            return "Cybersecurity"
        if any(k in name_l for k in ["frontend", "front-end", "react developer", "angular", "vue",
                                      "ui developer", "web developer", "ux", "ui/ux"]):
            return "Software Engineering"
        if any(k in name_l for k in ["backend", "back-end", "api developer", "java developer",
                                      "python developer", "node developer", "golang", "spring"]):
            return "Software Engineering"
        if any(k in name_l for k in ["full stack", "fullstack", "software engineer",
                                      "software developer", "sde"]):
            return "Software Engineering"
        if any(k in name_l for k in ["mobile", "android", "ios developer", "flutter", "react native"]):
            return "Mobile Development"
        if any(k in name_l for k in ["robotics", "autonomous", "embedded", "firmware", "iot developer",
                                      "plc", "scada", "automation engineer"]):
            return "Robotics & Automation"
        if any(k in name_l for k in ["mechanical", "cad", "solidworks", "autocad", "product design"]):
            return "Mechanical Engineering"
        if any(k in name_l for k in ["civil", "structural", "bim", "gis", "construction"]):
            return "Civil Engineering"
        if any(k in name_l for k in ["electrical", "power", "vlsi", "circuit"]):
            return "Electrical Engineering"
        if any(k in name_l for k in ["biomedical", "bioinformatics", "genomics", "clinical"]):
            return "Biomedical Engineering"
        if any(k in name_l for k in ["finance", "investment", "banking", "quant", "fintech", "actuar"]):
            return "Finance & Banking"
        if any(k in name_l for k in ["business analyst", "product manager", "project manager", "strategy"]):
            return "Business & Management"
        if any(k in name_l for k in ["marketing", "seo", "content creator", "social media", "digital marketing"]):
            return "Marketing"
        if any(k in name_l for k in ["quality assurance", "test engineer", "tester", "qa engineer"]):
            return "Quality Assurance"
        if any(k in name_l for k in ["blockchain", "web3", "solidity", "crypto"]):
            return "Blockchain"
        if any(k in name_l for k in ["game developer", "game designer", "unity", "unreal"]):
            return "Game Development"

        # ── Fall back to full text signals ────────────────────────────────
        if "artificial intelligence" in text_lower or "machine learning" in text_lower:
            return "Artificial Intelligence"
        if "cloud" in text_lower and ("aws" in text_lower or "azure" in text_lower or "gcp" in text_lower):
            return "Cloud & DevOps"
        if "cybersecurity" in text_lower or "cyber security" in text_lower:
            return "Cybersecurity"
        if "data" in text_lower and ("analytics" in text_lower or "analysis" in text_lower):
            return "Data & Analytics"
        if "software" in text_lower or "programming" in text_lower:
            return "Software Engineering"

        return "Technology"

    @staticmethod
    def _extract_category(career_name: str, text_lower: str) -> str:
        """
        Infer a high-level category (domain) from the career name.
        Intended for broad grouping: AI, Software, Data, Robotics, Cloud, Cyber,
        Finance, Design, etc.
        """
        name_l = career_name.strip().lower()

        # ── Exact single-word / acronym matches ──────────────────────────
        _exact_ai     = {"ai", "ml", "llm", "nlp", "gpt"}
        _exact_cloud  = {"aws", "gcp", "azure", "devops", "sre"}
        _exact_data   = {"bi", "etl", "olap"}
        _exact_iot    = {"iot", "plc", "scada", "rtos"}
        _exact_cyber  = {"soc", "siem"}
        _exact_qa     = {"qa", "qe", "sdet"}

        if name_l in _exact_ai:
            return "AI"
        if name_l in _exact_cloud:
            return "Cloud"
        if name_l in _exact_data:
            return "Data"
        if name_l in _exact_iot:
            return "Robotics"
        if name_l in _exact_cyber:
            return "Cybersecurity"
        if name_l in _exact_qa:
            return "QA"

        # ── Substring / prefix/suffix matches ────────────────────────────
        if any(k in name_l for k in ["artificial intelligence", "machine learning", "deep learning",
                                      "computer vision", "generative ai", "ai engineer", "ml engineer"]):
            return "AI"
        if name_l.startswith("ai ") or name_l.endswith(" ai"):
            return "AI"
        if any(k in name_l for k in ["data scientist", "data analyst", "data engineer",
                                      "analytics", "business intelligence"]):
            return "Data"
        if any(k in name_l for k in ["cloud", "devops", "sre", "platform engineer", "infrastructure"]):
            return "Cloud"
        if any(k in name_l for k in ["cyber", "security", "penetration", "infosec", "soc analyst"]):
            return "Cybersecurity"
        if any(k in name_l for k in ["frontend", "front-end", "backend", "back-end", "full stack",
                                      "fullstack", "software engineer", "software developer",
                                      "web developer", "mobile", "android", "ios developer",
                                      "flutter", "api developer", "sde"]):
            return "Software"
        if any(k in name_l for k in ["robotics", "autonomous", "embedded", "firmware",
                                      "iot developer", "plc", "automation"]):
            return "Robotics"
        if any(k in name_l for k in ["blockchain", "web3", "solidity"]):
            return "Blockchain"
        if any(k in name_l for k in ["game developer", "game designer", "unity", "unreal"]):
            return "Game Development"
        if any(k in name_l for k in ["ux", "ui designer", "product design", "figma"]):
            return "Design"
        if any(k in name_l for k in ["finance", "banking", "quant", "investment", "fintech", "actuar"]):
            return "Finance"
        if any(k in name_l for k in ["business analyst", "product manager", "project manager"]):
            return "Management"
        if any(k in name_l for k in ["marketing", "seo", "digital marketing"]):
            return "Marketing"
        if any(k in name_l for k in ["mechanical", "cad", "civil", "structural", "bim",
                                      "electrical", "biomedical"]):
            return "Engineering"
        if any(k in name_l for k in ["quality assurance", "test engineer", "tester", "qa engineer"]):
            return "QA"

        # ── Fall back to text signals ─────────────────────────────────────
        if "machine learning" in text_lower or "artificial intelligence" in text_lower:
            return "AI"
        if "software" in text_lower or "programming" in text_lower:
            return "Software"
        if "data" in text_lower:
            return "Data"

        return "Technology"

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

    # Removed _extract_salary and _extract_companies as they are no longer needed.

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
