# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/career_fact_extractor.py
#
# CareerFactExtractor — FULLY DETERMINISTIC (no LLM calls)
# Phase 9: Canonical career names + per-source skill synthesis
from __future__ import annotations

import logging
import re
import frappe
from job_search_ai.services.knowledge.extraction.career_canonicalizer import CareerCanonicalizer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword tables — deterministic, no LLM
# ---------------------------------------------------------------------------

INDUSTRY_KEYWORDS: dict[str, str] = {
    "fintech": "Finance Technology",
    "banking": "Banking & Finance",
    "finance": "Finance",
    "healthcare": "Healthcare",
    "health": "Healthcare",
    "medical": "Healthcare",
    "edtech": "Education Technology",
    "education": "Education",
    "ecommerce": "E-Commerce",
    "e-commerce": "E-Commerce",
    "retail": "Retail",
    "manufacturing": "Manufacturing",
    "automotive": "Automotive",
    "logistics": "Logistics & Supply Chain",
    "supply chain": "Logistics & Supply Chain",
    "cybersecurity": "Cybersecurity",
    "security": "Cybersecurity",
    "cloud": "Cloud Technology",
    "gaming": "Gaming",
    "media": "Media & Entertainment",
    "entertainment": "Media & Entertainment",
    "telecom": "Telecommunications",
    "consulting": "Consulting",
    "government": "Government",
    "defence": "Defence",
    "defense": "Defence",
    "aerospace": "Aerospace",
    "data": "Data & Analytics",
    "analytics": "Data & Analytics",
    "artificial intelligence": "Artificial Intelligence",
    "machine learning": "Artificial Intelligence",
    "blockchain": "Blockchain & Web3",
    "web3": "Blockchain & Web3",
    "iot": "Internet of Things",
    "internet of things": "Internet of Things",
    "software": "Technology",
    "technology": "Technology",
    "tech": "Technology",
    "information technology": "Technology",
}

CATEGORY_KEYWORDS: dict[str, str] = {
    "engineer": "Engineer",
    "engineering": "Engineer",
    "developer": "Developer",
    "development": "Developer",
    "programmer": "Developer",
    "analyst": "Analyst",
    "scientist": "Scientist",
    "architect": "Architect",
    "manager": "Manager",
    "designer": "Designer",
    "consultant": "Consultant",
    "researcher": "Researcher",
    "administrator": "Administrator",
    "tester": "Quality Assurance",
    "qa": "Quality Assurance",
    "devops": "DevOps",
    "security": "Security Specialist",
    "data": "Data Professional",
}

DEMAND_KEYWORDS: dict[str, str] = {
    "explosive growth": "Very High",
    "rapidly growing": "Very High",
    "very high demand": "Very High",
    "extremely high demand": "Very High",
    "skyrocketing": "Very High",
    "high demand": "High",
    "strong demand": "High",
    "growing demand": "High",
    "increasing demand": "High",
    "significant demand": "High",
    "moderate demand": "Medium",
    "steady demand": "Medium",
    "stable demand": "Medium",
    "low demand": "Low",
    "declining": "Low",
    "shrinking": "Low",
}

STAGE_KEYWORDS: dict[str, str] = {
    "immediate": "Immediate Placement",
    "entry level": "Immediate Placement",
    "entry-level": "Immediate Placement",
    "freshers": "Immediate Placement",
    "junior": "Immediate Placement",
    "placement": "Immediate Placement",
    "emerging": "Growing",
    "growing": "Growing",
    "evolving": "Growing",
    "developing": "Growing",
    "future": "Future",
    "next generation": "Future",
    "upcoming": "Future",
    "speculative": "Future",
    "research": "Future",
}

# Stage → suitable academic years
STAGE_TO_YEARS: dict[str, str] = {
    "Immediate Placement": "3,4",
    "Growing": "2,3,4",
    "Future": "1,2,3",
}

KNOWN_COMPANIES: list[str] = [
    "Google", "Microsoft", "Amazon", "Meta", "Apple", "Netflix", "Uber", "Airbnb",
    "IBM", "Oracle", "SAP", "Salesforce", "Adobe", "Accenture", "Deloitte",
    "Infosys", "TCS", "Wipro", "HCL", "Cognizant", "Tech Mahindra", "Capgemini",
    "Flipkart", "Swiggy", "Zomato", "Razorpay", "Paytm", "BYJU'S", "Ola",
    "Meesho", "Freshworks", "Zoho", "Persistent", "Mphasis", "Hexaware",
    "LinkedIn", "Twitter", "Atlassian", "GitHub", "Slack", "Zoom",
    "NVIDIA", "Intel", "Qualcomm", "Bosch", "Siemens",
    "JP Morgan", "Goldman Sachs", "Morgan Stanley", "HDFC", "ICICI", "Axis Bank",
    "Tesla", "SpaceX", "Boeing", "Airbus",
    "Samsung", "LG Electronics", "Sony",
    "Bain", "McKinsey", "BCG", "PwC", "EY", "KPMG",
]

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


# ---------------------------------------------------------------------------
# CareerFactExtractor
# ---------------------------------------------------------------------------

class CareerFactExtractor:
    """
    Extracts structured career facts from cleaned text deterministically.
    Phase 9: canonical names + per-source skill synthesis.
    No LLM calls. No network I/O. Pure Python heuristics.
    """

    @staticmethod
    def extract(cleaned_text: str, source_reliability: int, country: str) -> dict:
        results = CareerFactExtractor.extract_list(cleaned_text, source_reliability, country)
        return results[0] if results else {}

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
                else:
                    career_candidates = [default_career_name]
            else:
                fallback = CareerFactExtractor._fallback_career_name(paragraphs, country)
                canonical_fb = CareerCanonicalizer.canonicalize(fallback)
                if canonical_fb:
                    career_candidates = [canonical_fb]
                else:
                    career_candidates = ["Software Developer"]

        full_text_lower = cleaned_text.lower()
        industry  = CareerFactExtractor._extract_industry(full_text_lower)
        category  = CareerFactExtractor._extract_category(full_text_lower)
        demand    = CareerFactExtractor._extract_demand(full_text_lower)
        stage     = CareerFactExtractor._extract_stage(full_text_lower)
        summary   = ""  # DO NOT store summaries
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
            ) or industry
            career_category = CareerFactExtractor._extract_category(
                career_name.lower() + " " + full_text_lower
            ) or category

            results.append({
                "career_name":    career_name.strip(),
                "industry":       career_industry or "Technology",
                "category":       career_category or "Developer",
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

        job_keywords = re.compile(
            r'\b(engineer|developer|analyst|scientist|architect|manager|'
            r'designer|consultant|specialist|administrator|lead|senior|junior|'
            r'devops|fullstack|full.stack|frontend|back.?end|data|ml|ai|cloud|'
            r'security|qa|tester|researcher|intern)\b',
            re.IGNORECASE,
        )
        branch_keywords = re.compile(
            r'^(computer|mechanical|civil|electrical|electronics|chemical|'
            r'information technology|bca|mca|mba|b\.?tech|b\.?e\.?|'
            r'engineering|science|commerce|arts)\b',
            re.IGNORECASE,
        )
        _location_re = re.compile(
            r'^(hyderabad|bangalore|bengaluru|mumbai|delhi|pune|chennai|kolkata|'
            r'ahmedabad|noida|gurgaon|gurugram|india|usa|uk|dubai|singapore|'
            r'remote|work from home|wfh)\b',
            re.IGNORECASE,
        )
        _suffix_re = re.compile(
            r'\s*[—\-–|:]\s*(skills|career|guide|jobs|salary|2024|2025|2026|'
            r'trend|demand|scope|path|overview|top|best|review|report|hiring|'
            r'roadmap|comparison|vs\.?|versus|india|india 2025|india 2026).*$',
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
            if first_line and first_line[0].islower():
                continue
            if _location_re.match(first_line):
                continue
            if re.search(r'[—–‒\u2013\u2014]', first_line):
                continue
            if not job_keywords.search(first_line):
                continue
            if branch_keywords.match(first_line):
                continue

            # Canonicalize
            canonical = CareerFactExtractor._canonicalize_career_name(first_line)
            key = canonical.lower()
            if key not in seen_lower:
                seen_lower.add(key)
                candidates.append(canonical)

        return candidates

    @staticmethod
    def _fallback_career_name(paragraphs: list[str], country: str) -> str:
        for para in paragraphs:
            first = para.split('\n')[0].strip()
            first = re.sub(r'^#{1,4}\s*', '', first).strip()
            if 5 < len(first) < 80 and first[0].isupper():
                return CareerFactExtractor._canonicalize_career_name(first)
        return "Software Professional"

    @staticmethod
    def _extract_industry(text_lower: str) -> str:
        for kw, industry in INDUSTRY_KEYWORDS.items():
            if kw in text_lower:
                return industry
        return ""

    @staticmethod
    def _extract_category(text_lower: str) -> str:
        for kw, category in CATEGORY_KEYWORDS.items():
            if kw in text_lower:
                return category
        return ""

    @staticmethod
    def _extract_demand(text_lower: str) -> str:
        for phrase, demand in DEMAND_KEYWORDS.items():
            if phrase in text_lower:
                return demand
        high_signals = sum(1 for w in ["demand", "hiring", "opportunity", "grow", "expand"] if w in text_lower)
        if high_signals >= 3:
            return "High"
        return "Medium"

    @staticmethod
    def _extract_stage(text_lower: str) -> str:
        for phrase, stage in STAGE_KEYWORDS.items():
            if phrase in text_lower:
                return stage
        return "Growing"

    @staticmethod
    def _extract_summary(paragraphs: list[str]) -> str:
        _noise_re = re.compile(
            r'^(home|menu|search|login|register|contact|about|cookie|privacy|'
            r'terms|subscribe|newsletter|share|follow|tag|category|archive|'
            r'read more|click here|learn more|sign up|get started|view all|'
            r'back to|related|popular|recent|trending|next|previous|scroll)\b',
            re.IGNORECASE,
        )
        _heading_line_re = re.compile(
            r'^(engineer|developer|analyst|scientist|architect|manager|'
            r'designer|consultant|specialist|administrator|devops|fullstack|'
            r'frontend|backend|data|ml|ai|cloud|security|qa|tester|researcher|'
            r'web developer|software|machine learning|artificial intelligence|'
            r'top\s|what is|how to|salary|skills|career|guide|jobs|best|review)\b',
            re.IGNORECASE,
        )

        for para in paragraphs:
            lines = para.split('\n')
            body_lines = []
            for line in lines:
                stripped = re.sub(r'^#{1,4}\s*', '', line).strip()
                if not stripped or len(stripped) < 25:
                    continue
                if _heading_line_re.match(stripped):
                    continue
                if stripped.endswith('?') and len(stripped) < 120:
                    continue
                body_lines.append(stripped)

            if not body_lines:
                continue
            clean = ' '.join(body_lines)
            if _noise_re.match(clean) or clean.isupper():
                continue

            sentence_match = re.match(r'^([^.!?]+[.!?])', clean)
            if sentence_match:
                sentence = sentence_match.group(1).strip()
                if 20 <= len(sentence) <= 300:
                    return sentence
            if len(clean) >= 20:
                return clean[:250].strip()
        return ""

    @staticmethod
    def _extract_skills_per_source(sources: list[str]) -> dict[str, int]:
        """
        Extract raw skill tokens per source and return {token: source_count}.
        A skill mentioned in 3/5 sources gets source_count=3.
        Loads skill names and aliases dynamically from MariaDB.
        """
        token_source_counts: dict[str, int] = {}
        try:
            # Load active skill names and aliases from Skill Master and Skill Alias
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
            # Minimal hardcoded fallback to prevent complete failure if DB connection issue/bootstrap
            skill_words = {"python", "javascript", "typescript", "java", "c++", "docker", "kubernetes", "aws", "gcp", "azure", "sql", "git", "linux", "machine learning", "deep learning"}

        if not skill_words:
            # No Skill Master records found — use a baseline technology vocabulary
            # to ensure extraction can proceed.  This is preferable to returning
            # an empty dict which would cause validation to reject all careers.
            skill_words = {
                "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
                "docker", "kubernetes", "aws", "gcp", "azure", "sql", "nosql", "git",
                "linux", "react", "angular", "vue", "node", "django", "flask", "spring",
                "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "spark",
                "machine learning", "deep learning", "nlp", "computer vision",
                "html", "css", "restful", "graphql", "mongodb", "postgresql", "redis",
            }

        # Compile dynamic regex pattern sorting by length descending to match longest first
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
                # Reject if values look like years
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
                    # Reject single numbers that look like years (e.g., 2025)
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
        found = []
        for company in KNOWN_COMPANIES:
            if re.search(r'\b' + re.escape(company) + r'\b', text, re.IGNORECASE):
                found.append(company)
        return found

    @staticmethod
    def _extract_degrees_and_branches(text_lower: str) -> tuple[list[str], list[str]]:
        # Degrees
        degrees_found = set()
        if re.search(r'\b(engineering|b\.?tech|b\.?e\.?|m\.?tech|m\.?e\.?)\b', text_lower):
            degrees_found.add("Engineering")
        if re.search(r'\bbca\b', text_lower):
            degrees_found.add("BCA")
        if re.search(r'\bmca\b', text_lower):
            degrees_found.add("MCA")
        if re.search(r'\b(b\.?sc|m\.?sc|science)\b', text_lower):
            degrees_found.add("Science")
        if re.search(r'\b(bba|mba|business)\b', text_lower):
            degrees_found.add("Business Administration")
        if re.search(r'\bcommerce\b', text_lower):
            degrees_found.add("Commerce")

        # Fallback to standard baseline if nothing found
        if not degrees_found:
            degrees_found = {"Engineering", "BCA", "MCA"}

        # Branches
        branches_found = set()
        if re.search(r'\bcomputer (science|engineering)\b', text_lower) or re.search(r'\bcs[e]?\b', text_lower):
            branches_found.add("Computer Science")
            branches_found.add("Computer Engineering")
        if re.search(r'\binformation technology\b', text_lower) or re.search(r'\bit\b', text_lower):
            branches_found.add("Information Technology")
        if re.search(r'\bsoftware engineering\b', text_lower):
            branches_found.add("Software Engineering")
        if re.search(r'\bdata science\b', text_lower):
            branches_found.add("Data Science")
        if re.search(r'\bmechanical\b', text_lower):
            branches_found.add("Mechanical Engineering")
        if re.search(r'\bcivil\b', text_lower):
            branches_found.add("Civil Engineering")
        if re.search(r'\belectrical\b', text_lower):
            branches_found.add("Electrical Engineering")
        if re.search(r'\belectronics\b', text_lower):
            branches_found.add("Electronics Engineering")

        if not branches_found:
            branches_found = {"Computer Engineering", "Information Technology", "Computer Science"}

        return sorted(list(degrees_found)), sorted(list(branches_found))

