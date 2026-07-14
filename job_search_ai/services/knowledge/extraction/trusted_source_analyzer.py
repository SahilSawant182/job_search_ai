# -*- coding: utf-8 -*-
from urllib.parse import urlparse

class TrustedSourceAnalyzer:
    """
    Analyzes URLs/publishers to determine their reliability scores and capability mappings.
    Reliability score ranges from 0 to 100.
    Capabilities determine what kind of data the source can reliably provide.
    """

    # Domain to details mapping
    TRUSTED_DOMAINS = {
        "weforum.org": {
            "name": "World Economic Forum",
            "score": 99,
            "capabilities": {"career_titles", "skills", "hiring_trends", "industry"}
        },
        "mckinsey.com": {
            "name": "McKinsey",
            "score": 99,
            "capabilities": {"career_titles", "skills", "hiring_trends", "industry"}
        },
        "gartner.com": {
            "name": "Gartner",
            "score": 99,
            "capabilities": {"career_titles", "skills", "hiring_trends", "industry"}
        },
        "microsoft.com": {
            "name": "Microsoft Learn",
            "score": 97,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "aws.amazon.com": {
            "name": "AWS Learn",
            "score": 97,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "amazon.com": {
            "name": "AWS Learn",
            "score": 97,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "developers.google.com": {
            "name": "Google Developers",
            "score": 97,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "google.com": {
            "name": "Google Developers",
            "score": 97,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "linkedin.com": {
            "name": "LinkedIn",
            "score": 96,
            "capabilities": {"career_titles", "skills", "hiring_trends", "companies", "salary", "industry"}
        },
        "github.com": {
            "name": "GitHub",
            "score": 95,
            "capabilities": {"skills", "technology"}
        },
        "oracle.com": {
            "name": "Oracle",
            "score": 95,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "ibm.com": {
            "name": "IBM",
            "score": 95,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "nvidia.com": {
            "name": "NVIDIA",
            "score": 95,
            "capabilities": {"skills", "career_titles", "technology"}
        },
        "coursera.org": {
            "name": "Coursera",
            "score": 92,
            "capabilities": {"skills", "career_titles", "qualifications"}
        },
        "stackoverflow.com": {
            "name": "StackOverflow",
            "score": 90,
            "capabilities": {"skills", "technology"}
        },
        "glassdoor.com": {
            "name": "Glassdoor",
            "score": 85,
            "capabilities": {"career_titles", "skills", "hiring_trends", "companies", "salary"}
        },
        "naukri.com": {
            "name": "Naukri",
            "score": 82,
            "capabilities": {"career_titles", "skills", "hiring_trends", "companies", "salary"}
        },
        "indeed.com": {
            "name": "Indeed",
            "score": 80,
            "capabilities": {"career_titles", "skills", "hiring_trends", "companies", "salary"}
        },
        "medium.com": {
            "name": "Medium",
            "score": 55,
            "capabilities": {"skills", "technology"}
        }
    }

    @staticmethod
    def analyze(url: str, publisher_name: str = None) -> dict:
        """
        Analyze a URL and/or publisher name.
        Returns a dict:
        {
            "reliability_score": int,
            "capabilities": set,
            "publisher": str
        }
        """
        if not url:
            return {
                "reliability_score": 30,
                "capabilities": set(),
                "publisher": publisher_name or "Unknown Source"
            }

        # Parse domain
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            domain = ""

        # Match domain or partial match
        matched_details = None
        for td, details in TrustedSourceAnalyzer.TRUSTED_DOMAINS.items():
            if td in domain or (publisher_name and td in publisher_name.lower()):
                matched_details = details
                break

        if matched_details:
            return {
                "reliability_score": matched_details["score"],
                "capabilities": matched_details["capabilities"],
                "publisher": matched_details["name"]
            }

        # Default fallback score for arbitrary sites
        return {
            "reliability_score": 30,
            "capabilities": {"skills", "career_titles"},
            "publisher": publisher_name or domain or "Blog/Web Source"
        }
