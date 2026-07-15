# -*- coding: utf-8 -*-
import re

class CompanyExtractor:
    """
    Extracts, filters, and normalizes hiring companies from candidate strings.
    Ignores publishers, universities, news sites, and documentation sites.
    """

    # Generic categories for non-hiring entities
    EDU_PATTERNS = [
        r"university", r"college", r"school", r"academy", r"institute",
        r"course", r"training", r"bootcamp"
    ]
    
    PUBLISHER_PATTERNS = [
        r"blog", r"medium", r"news", r"daily", r"times", r"press",
        r"documentation", r"tutorial", r"guide", r"wiki", r"book",
        r"wikipedia", r"youtube", r"github", r"stackoverflow", r"reddit",
        r"forum", r"society"
    ]
    
    PORTAL_PATTERNS = [
        r"linkedin", r"glassdoor", r"indeed", r"naukri", r"monster", 
        r"foundit", r"job", r"career", r"portal"
    ]

    EXCLUDED_PATTERNS = EDU_PATTERNS + PUBLISHER_PATTERNS + PORTAL_PATTERNS

    # Standard known employer suffix cleanup
    CLEANUP_SUFFIXES = [
        r"\binc\b\.?", r"\bcorp\b\.?", r"\bcorporation\b", r"\bllc\b", r"\bltd\b\.?", r"\bco\b\.?", r"\bplc\b"
    ]

    @staticmethod
    def extract_and_filter(candidates: list) -> list:
        """
        Filters and normalizes a list of candidate company names.
        """
        if not candidates:
            return []

        filtered_companies = set()
        for cand in candidates:
            if not cand:
                continue

            cand_clean = cand.strip()
            cand_lower = cand_clean.lower()

            # 1. Ignore if matching excluded patterns (universities, publishers, etc.)
            is_excluded = False
            for pat in CompanyExtractor.EXCLUDED_PATTERNS:
                if re.search(pat, cand_lower):
                    is_excluded = True
                    break
            if is_excluded:
                continue

            # 2. Normalize: Remove suffix business entity types (Inc., LLC, Ltd., etc.)
            for suffix in CompanyExtractor.CLEANUP_SUFFIXES:
                cand_clean = re.sub(suffix, "", cand_clean, flags=re.IGNORECASE).strip()
            
            # Clean up trailing/leading commas or special characters
            cand_clean = re.sub(r'^[\s,\-\.]+|[\s,\-\.]+$', "", cand_clean).strip()

            # 3. Final validation: must be non-empty and reasonably sized (usually 2 to 40 chars)
            if cand_clean and 2 <= len(cand_clean) <= 40:
                # Deduplicate using title casing
                filtered_companies.add(cand_clean.title())

        return sorted(list(filtered_companies))
