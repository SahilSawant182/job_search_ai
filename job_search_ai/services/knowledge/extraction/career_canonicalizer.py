# -*- coding: utf-8 -*-
import re

class CareerCanonicalizer:
    """
    Normalises candidate job titles to canonical career names.

    Responsibility: name normalisation ONLY.
    Removes marketing noise words, standardises spacing, casing, and punctuation.
    Rejects strings that cannot represent a real career title.

    Must NOT contain: synonym dictionaries, career mappings, academic lists,
    or other domain knowledge.
    """

    @classmethod
    def _clean_title(cls, title: str) -> str | None:
        t = title.strip()
        if not t:
            return None

        # Remove obvious marketing/SEO prefix patterns
        marketing_prefixes = [
            r"^how to become a(?:n)?\b",
            r"^become a(?:n)?\b",
            r"^career as a(?:n)?\b",
            r"^what is a(?:n)?\b",
            r"^the demand for a(?:n)?\b",
            r"^the role of a(?:n)?\b",
            r"^role of a(?:n)?\b",
            r"^guide to\b",
            r"^complete guide to\b",
        ]
        for pattern in marketing_prefixes:
            t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()

        # Remove obvious marketing/SEO suffix patterns
        marketing_suffixes = [
            r"\bsalary guide\b.*",
            r"\bsalary in\b.*",
            r"\binterview questions\b.*",
            r"\bcareer path\b.*",
            r"\broadmap\b.*",
            r"\btutorial\b.*",
            r"\bcourse\b.*",
            r"\bresume\b.*",
            r"\bfor beginners?\b.*",
            r"\bscope\b.*",
            r"\bguide\b.*",
        ]
        for pattern in marketing_suffixes:
            t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()

        # Remove years/dates
        t = re.sub(r"\b(2024|2025|2026)\b", "", t, flags=re.IGNORECASE).strip()

        # Clean punctuation except standard career symbols /+#-
        t = re.sub(r"[^\w\s\-\/\+]", " ", t)

        # Standardise spacing
        t = " ".join(t.split())
        return t if t else None

    @classmethod
    def canonicalize(cls, title: str) -> str | None:
        """
        Clean, normalize title casing, and return canonical name.
        """
        if not title:
            return None

        cleaned = cls._clean_title(title)
        if not cleaned:
            return None

        if cls.is_marketing_title(cleaned):
            return None

        # Capitalize each word nicely
        words = cleaned.split()
        capitalized_words = []
        for w in words:
            # If word is already all caps (e.g. AI, ML, UI, UX, QA, CA, HR, BI, SRE, IT), keep it as is
            if w.isupper() and len(w) <= 4:
                capitalized_words.append(w)
            elif w.lower() in ("c++", "c#", ".net"):
                capitalized_words.append(w.upper())
            else:
                capitalized_words.append(w.capitalize())

        canonical_name = " ".join(capitalized_words)
        return canonical_name if canonical_name else None

    @classmethod
    def is_marketing_title(cls, title: str) -> bool:
        """
        Checks if a title looks like a marketing/article title.
        """
        t = title.strip().lower()
        marketing_keywords = [
            "guide", "salary guide", "interview questions", "how to", "top 10", "top 5",
            "best", "roadmap", "tutorial", "course", "become", "complete guide", "syllabus",
            "resume", "vs", "versus"
        ]
        for kw in marketing_keywords:
            if kw in t:
                return True

        # Reject if the title contains more than 5 words
        words = t.split()
        if len(words) > 5:
            return True

        # Reject sentence-like headers containing lowercase verbs or transition words
        sentence_verbs = [
            "is", "are", "was", "were", "has", "have", "had", "will", "should", "would",
            "can", "could", "want", "learn", "need", "needs", "used", "uses", "offers",
            "provides", "become", "about"
        ]
        for verb in sentence_verbs:
            if re.search(r'\b' + re.escape(verb) + r'\b', t):
                return True

        return False
