# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/extraction/career_fact_extractor.py
#
# CareerFactExtractor — FULLY DETERMINISTIC (no LLM calls)
# Phase 9: Canonical career names + per-source skill synthesis
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical career name table
# ---------------------------------------------------------------------------

CANONICAL_CAREERS: dict[str, str] = {
    # Frontend
    "frontend developer": "Frontend Developer",
    "front-end developer": "Frontend Developer",
    "front end developer": "Frontend Developer",
    "ui developer": "Frontend Developer",
    "react developer": "React Developer",
    "angular developer": "Angular Developer",
    "vue developer": "Vue.js Developer",
    # Backend
    "backend developer": "Backend Developer",
    "back-end developer": "Backend Developer",
    "back end developer": "Backend Developer",
    "server-side developer": "Backend Developer",
    "node developer": "Node.js Developer",
    "django developer": "Python Backend Developer",
    "spring developer": "Java Backend Developer",
    # Full Stack
    "full stack developer": "Full Stack Developer",
    "fullstack developer": "Full Stack Developer",
    "full-stack developer": "Full Stack Developer",
    "mern developer": "Full Stack Developer",
    "mean developer": "Full Stack Developer",
    # Data
    "data scientist": "Data Scientist",
    "data analyst": "Data Analyst",
    "data engineer": "Data Engineer",
    "business analyst": "Business Analyst",
    "bi developer": "Business Intelligence Developer",
    "bi analyst": "Business Intelligence Analyst",
    # AI / ML
    "machine learning engineer": "Machine Learning Engineer",
    "ml engineer": "Machine Learning Engineer",
    "ai engineer": "AI Engineer",
    "artificial intelligence engineer": "AI Engineer",
    "deep learning engineer": "Deep Learning Engineer",
    "nlp engineer": "NLP Engineer",
    "computer vision engineer": "Computer Vision Engineer",
    # Cloud / DevOps
    "cloud engineer": "Cloud Engineer",
    "devops engineer": "DevOps Engineer",
    "site reliability engineer": "Site Reliability Engineer",
    "sre": "Site Reliability Engineer",
    "platform engineer": "Platform Engineer",
    "infrastructure engineer": "Infrastructure Engineer",
    # Mobile
    "android developer": "Android Developer",
    "ios developer": "iOS Developer",
    "mobile developer": "Mobile Developer",
    "flutter developer": "Flutter Developer",
    "react native developer": "React Native Developer",
    # Software Engineering
    "software engineer": "Software Engineer",
    "software developer": "Software Developer",
    "application developer": "Software Developer",
    "java developer": "Java Developer",
    "python developer": "Python Developer",
    "golang developer": "Go Developer",
    ".net developer": ".NET Developer",
    # Security
    "cybersecurity analyst": "Cybersecurity Analyst",
    "security engineer": "Security Engineer",
    "penetration tester": "Penetration Tester",
    "ethical hacker": "Penetration Tester",
    # QA / Testing
    "qa engineer": "QA Engineer",
    "test engineer": "QA Engineer",
    "automation tester": "Automation Test Engineer",
    "sdet": "Automation Test Engineer",
    # Design
    "ui/ux designer": "UI/UX Designer",
    "ux designer": "UI/UX Designer",
    "ui designer": "UI/UX Designer",
    "product designer": "Product Designer",
    # Management
    "product manager": "Product Manager",
    "project manager": "Project Manager",
    "engineering manager": "Engineering Manager",
    # Database
    "database administrator": "Database Administrator",
    "dba": "Database Administrator",
    "database engineer": "Database Engineer",
    # Embedded
    "embedded systems engineer": "Embedded Systems Engineer",
    "firmware engineer": "Firmware Engineer",
    "iot engineer": "IoT Engineer",
    # Other tech
    "blockchain developer": "Blockchain Developer",
    "web3 developer": "Web3 Developer",
    "game developer": "Game Developer",
    "technical writer": "Technical Writer",
}

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
    ) -> list[dict]:
        """
        Extract career facts. source_texts is a list of individual source page texts
        for per-source skill frequency counting. Falls back to [cleaned_text] if omitted.
        """
        if not cleaned_text or not cleaned_text.strip():
            return []

        sources = source_texts if source_texts else [cleaned_text]
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', cleaned_text) if p.strip()]

        career_candidates = CareerFactExtractor._extract_career_titles(paragraphs)
        if not career_candidates:
            career_candidates = [CareerFactExtractor._fallback_career_name(paragraphs, country)]

        full_text_lower = cleaned_text.lower()
        industry  = CareerFactExtractor._extract_industry(full_text_lower)
        category  = CareerFactExtractor._extract_category(full_text_lower)
        demand    = CareerFactExtractor._extract_demand(full_text_lower)
        stage     = CareerFactExtractor._extract_stage(full_text_lower)
        summary   = CareerFactExtractor._extract_summary(paragraphs)
        salaries  = CareerFactExtractor._extract_salary(full_text_lower, country)

        # Per-source skill extraction — returns {raw_token: source_count}
        skill_freq = CareerFactExtractor._extract_skills_per_source(sources)

        companies = CareerFactExtractor._extract_companies(cleaned_text)
        evidence_count = len(paragraphs)
        suitable_years = STAGE_TO_YEARS.get(stage or "Growing", "2,3,4")

        complete_fields = sum([bool(industry), bool(category), bool(demand), bool(skill_freq), bool(summary)])
        completeness = int((complete_fields / 5) * 100)
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
            career_summary = summary[:297] + "..." if len(summary) > 297 else summary

            results.append({
                "career_name":    career_name.strip(),
                "industry":       career_industry or "Technology",
                "category":       career_category or "Developer",
                "demand":         demand or "Medium",
                "stage":          stage or "Growing",
                "summary":        career_summary,
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
        """Map a raw title candidate to a canonical career name via token overlap."""
        raw_lower = raw.lower().strip()

        # Direct match first
        if raw_lower in CANONICAL_CAREERS:
            return CANONICAL_CAREERS[raw_lower]

        # Token overlap: find canonical entry with highest word overlap
        raw_tokens = set(re.split(r'[\s/\-]+', raw_lower))
        best_match = None
        best_overlap = 0

        for key, canonical in CANONICAL_CAREERS.items():
            key_tokens = set(re.split(r'[\s/\-]+', key))
            overlap = len(raw_tokens & key_tokens)
            total = len(raw_tokens | key_tokens)
            if total > 0 and overlap / total >= 0.60 and overlap > best_overlap:
                best_overlap = overlap
                best_match = canonical

        return best_match if best_match else raw

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
        """
        token_source_counts: dict[str, int] = {}
        for src_text in sources:
            found_in_this_source: set[str] = set()
            for pattern in SKILL_PATTERNS:
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
                result["min"] = float(m.group("min").replace(",", ""))
                result["max"] = float(m.group("max").replace(",", ""))
            except (ValueError, AttributeError):
                pass
        if "min" not in result:
            m2 = _SALARY_SINGLE_RE.search(text_lower)
            if m2:
                try:
                    result["min"] = float(m2.group("amount").replace(",", ""))
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
