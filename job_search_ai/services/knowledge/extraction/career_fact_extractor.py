# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/career_fact_extractor.py
#
# CareerFactExtractor — FULLY DETERMINISTIC (no LLM calls)
# ---------------------------------------------------------
# Extracts career facts from cleaned web-page text using only
# Python heuristics. Zero LLM calls. Zero network I/O.
#
# Architecture principle: ONE USER REQUEST = ONE LLM CALL
#   - The LLM is called exactly once per student request,
#     at the final recommendation generation stage.
#   - Everything before that call must be deterministic Python.
#
# What this module extracts deterministically
# -------------------------------------------
#   career_name   — inferred from titles / headings in the text
#   industry      — matched from INDUSTRY_KEYWORDS
#   category      — matched from CATEGORY_KEYWORDS
#   demand        — matched from DEMAND_KEYWORDS
#   stage         — matched from STAGE_KEYWORDS
#   summary       — first substantive sentence (≤300 chars)
#   min/max_salary — extracted via salary regex
#   currency      — inferred from salary context
#   skills        — raw token list (normalised later by SkillNormalizer)
#   companies     — matched from KNOWN_COMPANIES
#   evidence_count — number of source texts that yielded evidence
#   confidence    — deterministic formula: source_reliability + completeness

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword tables — all deterministic, no LLM
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
    "it ": "Technology",
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
    "qa ": "Quality Assurance",
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

# Representative companies (extend as needed; keep deterministic)
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

# Skill token patterns (raw strings; normalised later by SkillNormalizer)
SKILL_PATTERNS: list[re.Pattern] = [
    re.compile(r'\b(' + '|'.join([
        r'python', r'java(?:script)?', r'typescript', r'golang?', r'rust', r'ruby',
        r'php', r'swift', r'kotlin', r'scala', r'c\+\+', r'c#', r'\.net',
        r'react(?:\.?js)?', r'angular(?:\.?js)?', r'vue(?:\.?js)?', r'next\.?js',
        r'node(?:\.?js)?', r'express(?:\.?js)?', r'django', r'flask', r'fastapi',
        r'spring boot', r'laravel',
        r'sql', r'mysql', r'postgresql', r'mongodb', r'redis', r'cassandra',
        r'elasticsearch', r'graphql', r'rest(?:ful)? api',
        r'docker', r'kubernetes', r'terraform', r'ansible', r'jenkins',
        r'aws', r'azure', r'gcp', r'google cloud',
        r'git', r'linux', r'bash', r'shell scripting',
        r'machine learning', r'deep learning', r'tensorflow', r'pytorch',
        r'scikit-learn', r'pandas', r'numpy', r'spark', r'hadoop',
        r'html5?', r'css3?', r'sass', r'tailwind(?:css)?', r'bootstrap',
        r'figma', r'sketch', r'photoshop', r'illustrator',
        r'agile', r'scrum', r'jira', r'ci/cd',
        r'microservices', r'devops', r'devsecops',
        r'nlp', r'computer vision', r'opencv',
        r'tableau', r'power bi', r'excel',
        r'blockchain', r'solidity', r'web3\.?js',
        r'android', r'ios', r'react native', r'flutter',
        r'cyber security', r'cybersecurity', r'penetration testing',
        r'data analysis', r'data visualization', r'etl',
        r'communication', r'leadership', r'problem solving', r'teamwork',
    ]) + r')\b',
    re.IGNORECASE,
    )
]

# Salary extraction pattern
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

    No LLM calls. No network I/O. Pure Python heuristics.

    Architecture principle:
        The LLM is called exactly once per student request — only during
        final recommendation generation.  This extractor performs all
        pre-processing work deterministically so no additional inference
        is required inside the knowledge pipeline.
    """

    @staticmethod
    def extract(cleaned_text: str, source_reliability: int, country: str) -> dict:
        """
        Extract a single career facts dict from cleaned text.

        For backward compatibility — returns the first item from extract_list().
        Most callers should use extract_list() to get all extracted careers.
        """
        results = CareerFactExtractor.extract_list(cleaned_text, source_reliability, country)
        return results[0] if results else {}

    @staticmethod
    def extract_list(
        cleaned_text: str,
        source_reliability: int,
        country: str,
    ) -> list[dict]:
        """
        Extract a list of career fact dicts from cleaned text.

        One call to this method processes all source text at once.
        Returns a list so KnowledgeBuilder can persist multiple careers
        from a single Tavily batch.

        Parameters
        ----------
        cleaned_text   : str  — already cleaned by ContentCleaner
        source_reliability : int — aggregate reliability score (0-100)
        country        : str  — target country (used for currency inference)

        Returns
        -------
        list[dict] — one dict per distinct career detected in the text.
            Each dict contains:
                career_name, industry, category, demand, stage,
                summary, min_salary, max_salary, currency,
                skills (raw list), companies (raw list),
                evidence_count, confidence
        """
        if not cleaned_text or not cleaned_text.strip():
            return []

        # Split text into paragraphs for per-paragraph analysis
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', cleaned_text) if p.strip()]

        # ---------------------------------------------------------------
        # Pass 1 — Extract career title candidates from headings/titles
        # ---------------------------------------------------------------
        career_candidates = CareerFactExtractor._extract_career_titles(paragraphs)

        if not career_candidates:
            # Fallback: treat the whole text as describing one career
            # Use the dominant noun phrase from the first heading
            career_candidates = [CareerFactExtractor._fallback_career_name(paragraphs, country)]

        # ---------------------------------------------------------------
        # Pass 2 — For each career candidate, extract metadata
        # ---------------------------------------------------------------
        full_text_lower = cleaned_text.lower()

        industry  = CareerFactExtractor._extract_industry(full_text_lower)
        category  = CareerFactExtractor._extract_category(full_text_lower)
        demand    = CareerFactExtractor._extract_demand(full_text_lower)
        stage     = CareerFactExtractor._extract_stage(full_text_lower)
        summary   = CareerFactExtractor._extract_summary(paragraphs)
        salaries  = CareerFactExtractor._extract_salary(full_text_lower, country)
        skills    = CareerFactExtractor._extract_skills(cleaned_text)
        companies = CareerFactExtractor._extract_companies(cleaned_text)
        evidence_count = len(paragraphs)

        # ---------------------------------------------------------------
        # Pass 3 — Compute deterministic confidence score
        # ---------------------------------------------------------------
        complete_fields = sum([
            bool(industry),
            bool(category),
            bool(demand),
            bool(skills),
            bool(summary),
        ])
        completeness = int((complete_fields / 5) * 100)
        confidence = min(100, int(source_reliability * 0.55 + completeness * 0.45))

        # ---------------------------------------------------------------
        # Build result dicts — one per career candidate
        # ---------------------------------------------------------------
        results = []
        for career_name in career_candidates[:3]:  # cap at 3 careers per batch
            if not career_name or not career_name.strip():
                continue

            # Derive a per-career industry / category if the career name
            # gives stronger signals than the general text
            career_industry = CareerFactExtractor._extract_industry(
                career_name.lower() + " " + full_text_lower
            ) or industry
            career_category = CareerFactExtractor._extract_category(
                career_name.lower() + " " + full_text_lower
            ) or category

            # Enforce summary length ≤ 300 chars
            career_summary = summary[:297] + "..." if len(summary) > 297 else summary

            results.append({
                "career_name":    career_name.strip(),
                "industry":       career_industry or "Technology",
                "category":       career_category or "Developer",
                "demand":         demand or "Medium",
                "stage":          stage or "Growing",
                "summary":        career_summary,
                "min_salary":     salaries.get("min"),
                "max_salary":     salaries.get("max"),
                "currency":       salaries.get("currency", "INR" if "india" in full_text_lower else "USD"),
                "skills":         skills,
                "companies":      companies,
                "evidence_count": max(1, evidence_count),
                "confidence":     confidence,
            })

        return results

    # ------------------------------------------------------------------
    # Private helpers — all deterministic Python, zero LLM calls
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_career_titles(paragraphs: list[str]) -> list[str]:
        """
        Extract career/job title candidates from markdown headings and
        lines that contain title-case noun phrases with job keywords.
        """
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
            r'information technology|it|bca|mca|mba|b\.?tech|b\.?e\.?|'
            r'engineering|science|commerce|arts)\b',
            re.IGNORECASE,
        )

        # Reject headings that start with a location/city name (e.g. "Hyderabad – DevOps")
        _location_re = re.compile(
            r'^(hyderabad|bangalore|bengaluru|mumbai|delhi|pune|chennai|kolkata|'
            r'ahmedabad|noida|gurgaon|gurugram|india|usa|uk|dubai|singapore|'
            r'remote|work from home|wfh)\b',
            re.IGNORECASE,
        )

        # Strip decorative suffixes ONLY when preceded by a clear separator (—, –, -, |, :)
        # Using a separator requirement prevents over-stripping like "Data Scientist Guide" -> ""
        _suffix_re = re.compile(
            r'\s*[—\-–|:]\s*(skills|career|guide|jobs|salary|2024|2025|2026|'
            r'trend|demand|scope|path|overview|top|best|review|report|hiring|'
            r'roadmap|comparison|vs\.?|versus|india|india 2025|india 2026).*$',
            re.IGNORECASE,
        )

        for para in paragraphs:
            first_line = para.split('\n')[0].strip()
            # Remove markdown heading markers
            first_line = re.sub(r'^#{1,4}\s*', '', first_line).strip()
            # Strip heading decorative suffixes
            first_line = _suffix_re.sub('', first_line).strip()

            # Length constraints — job titles are 4–60 chars
            if len(first_line) < 4 or len(first_line) > 60:
                continue

            # Reject sentences (end with period, comma, question mark, or start with lowercase)
            if first_line.endswith(('.', ',', '?', '!')):
                continue
            if first_line and first_line[0].islower():
                continue

            # Reject location-prefixed headings (e.g. "Hyderabad – DevOps & Cloud-based projects")
            if _location_re.match(first_line):
                continue

            # If ANY em/en-dash remains after suffix stripping, it's a location/comparison heading
            if re.search(r'[—–‒\u2013\u2014]', first_line):
                continue

            # Must contain a job keyword
            if not job_keywords.search(first_line):
                continue

            # Must NOT be a branch/degree name
            if branch_keywords.match(first_line):
                continue

            key = first_line.lower()
            if key not in seen_lower:
                seen_lower.add(key)
                candidates.append(first_line)

        return candidates

    @staticmethod
    def _fallback_career_name(paragraphs: list[str], country: str) -> str:
        """Return a best-guess career name when heading extraction yields nothing."""
        for para in paragraphs:
            first = para.split('\n')[0].strip()
            first = re.sub(r'^#{1,4}\s*', '', first).strip()
            if 5 < len(first) < 80 and first[0].isupper():
                return first
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
        # Count occurrence of generic positive signals
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
        """Extract the first substantive sentence as the career summary (≤300 chars).

        Skips markdown headings and navigation/SEO noise lines.
        Picks the first sentence that reads like a real career description.
        """
        _noise_re = re.compile(
            r'^(home|menu|search|login|register|contact|about|cookie|privacy|'
            r'terms|subscribe|newsletter|share|follow|tag|category|archive|'
            r'read more|click here|learn more|sign up|get started|view all|'
            r'back to|related|popular|recent|trending|next|previous|scroll)\b',
            re.IGNORECASE,
        )
        # Job title / heading pattern — lines that look like a title, not a description
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
                if not stripped:
                    continue
                # Skip short lines (likely a heading or navigation item)
                if len(stripped) < 25:
                    continue
                # Skip lines that look like page titles or career name headings
                if _heading_line_re.match(stripped):
                    continue
                # Skip question/title lines
                if stripped.endswith('?') and len(stripped) < 120:
                    continue
                body_lines.append(stripped)

            if not body_lines:
                continue

            clean = ' '.join(body_lines)

            # Skip navigation/menu noise
            if _noise_re.match(clean):
                continue

            # Skip lines that are all-uppercase (often headings/callouts)
            if clean.isupper():
                continue

            # Take the first proper sentence
            sentence_match = re.match(r'^([^.!?]+[.!?])', clean)
            if sentence_match:
                sentence = sentence_match.group(1).strip()
                if 20 <= len(sentence) <= 300:
                    return sentence

            # Fallback: first 250 chars of meaningful text
            if len(clean) >= 20:
                return clean[:250].strip()

        return ""

    @staticmethod
    def _extract_salary(text_lower: str, country: str) -> dict:
        """Extract min/max salary and currency using regex (deterministic)."""
        result: dict = {}

        # Range extraction
        m = _SALARY_RE.search(text_lower)
        if m:
            try:
                result["min"] = float(m.group("min").replace(",", ""))
                result["max"] = float(m.group("max").replace(",", ""))
            except (ValueError, AttributeError):
                pass

        # Single value fallback
        if "min" not in result:
            m2 = _SALARY_SINGLE_RE.search(text_lower)
            if m2:
                try:
                    amount = float(m2.group("amount").replace(",", ""))
                    result["min"] = amount
                except (ValueError, AttributeError):
                    pass

        # Currency inference
        if "inr" in text_lower or "lakh" in text_lower or "lpa" in text_lower or "india" in text_lower:
            result["currency"] = "INR"
        elif "usd" in text_lower or "dollar" in text_lower or "united states" in text_lower:
            result["currency"] = "USD"
        elif "gbp" in text_lower or "pound" in text_lower:
            result["currency"] = "GBP"
        elif "eur" in text_lower or "euro" in text_lower:
            result["currency"] = "EUR"
        elif country and "india" in country.lower():
            result["currency"] = "INR"
        else:
            result["currency"] = "USD"

        return result

    @staticmethod
    def _extract_skills(text: str) -> list[str]:
        """
        Extract raw skill tokens from text using pattern matching.
        These are raw strings; SkillNormalizer maps them to canonical names.
        """
        found: set[str] = set()
        for pattern in SKILL_PATTERNS:
            for m in pattern.finditer(text):
                tok = m.group(0).strip()
                if tok:
                    found.add(tok.lower())
        return sorted(found)

    @staticmethod
    def _extract_companies(text: str) -> list[str]:
        """Extract known company names mentioned in the text."""
        found = []
        for company in KNOWN_COMPANIES:
            if re.search(r'\b' + re.escape(company) + r'\b', text, re.IGNORECASE):
                found.append(company)
        return found
