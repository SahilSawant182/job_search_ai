# -*- coding: utf-8 -*-
import re

class CareerCanonicalizer:
    """
    Normalises candidate job titles to canonical career names.

    Responsibility: name normalisation ONLY.
    Removes marketing noise words, expands abbreviations, standardises
    spacing, casing, and punctuation.  Rejects strings that cannot
    represent a real career title.

    Must NOT contain: skill lists, industry mappings, career profiles,
    or any other domain knowledge beyond title string cleaning.
    """

    # Degree-agnostic general abbreviation expansions (logical rules, not career profiles)
    ABBREVIATIONS = {
        r"\bml\b": "Machine Learning",
        r"\bai\b": "Artificial Intelligence",
        r"\bdevops\b": "DevOps",
        r"\bqa\b": "QA",
        r"\bui/ux\b": "UI/UX",
        r"\bui\b": "UI",
        r"\bux\b": "UX",
        r"\bbi\b": "BI",
        r"\bsre\b": "Site Reliability Engineering",
        r"\bca\b": "Chartered Accountant",
        r"\bhr\b": "HR",
    }

    SYNONYMS = {
        r"\bfrontend (?:engineer|developer|specialist|designer|coder|programmer)\b": "Frontend Developer",
        r"\bui (?:engineer|developer|specialist|designer)\b": "Frontend Developer",
        r"\breact (?:engineer|developer|specialist)\b": "Frontend Developer",
        r"\bux (?:engineer|developer|specialist|designer)\b": "UI/UX Designer",
        r"\bui/ux (?:engineer|developer|specialist|designer)\b": "UI/UX Designer",
        r"\bbackend (?:engineer|developer|specialist|coder|programmer)\b": "Backend Developer",
        r"\bnodejs? (?:engineer|developer|specialist)\b": "Backend Developer",
        r"\bpython (?:engineer|developer|specialist)\b": "Backend Developer",
        r"\bjava (?:engineer|developer|specialist)\b": "Backend Developer",
        r"\bfull[\s\-]*stack (?:engineer|developer|specialist|coder|programmer)\b": "Full Stack Developer",
        r"\bmern (?:stack )?(?:engineer|developer|specialist)\b": "Full Stack Developer",
        r"\bdevops (?:engineer|specialist|architect)\b": "DevOps Engineer",
        r"\bsite reliability (?:engineer|specialist)\b": "DevOps Engineer",
        r"\bsre\b": "DevOps Engineer",
        r"\bcloud (?:devops|engineer|architect|specialist)\b": "DevOps Engineer",
        r"\bdata scientist\b": "Data Scientist",
        r"\bdata science (?:professional|specialist|engineer)\b": "Data Scientist",
        r"\bdata analyst\b": "Data Analyst",
        r"\bbusiness intelligence analyst\b": "Data Analyst",
        r"\bbi analyst\b": "Data Analyst",
        r"\bmachine learning (?:engineer|specialist|developer)\b": "Machine Learning Engineer",
        r"\bml (?:engineer|specialist|developer)\b": "Machine Learning Engineer",
        r"\bartificial intelligence (?:engineer|specialist|developer)\b": "Machine Learning Engineer",
        r"\bai (?:engineer|specialist|developer)\b": "Machine Learning Engineer",
        r"\bai/ml (?:engineer|specialist|developer)\b": "Machine Learning Engineer",
    }

    @classmethod
    def canonicalize(cls, title: str) -> str | None:
        """
        Takes a raw extracted title, cleans it, rejects marketing noise,
        standardizes terminology, and returns the canonicalized career name.
        """
        if not title:
            return None

        # Clean string: lowercase, strip punctuation
        t = title.strip().lower()

        # Check synonyms first
        for pattern, canonical in cls.SYNONYMS.items():
            if re.search(pattern, t):
                return canonical

        # Remove common years
        t = re.sub(r'\b(2024|2025|2026)\b', '', t)

        # Basic cleaning of non-word chars
        t = re.sub(r'[^\w\s\-\/\+]', ' ', t)
        t = " ".join(t.split())

        # Clean common marketing/article noise words
        noise_words = [
            r"\bguide(?:lines)?\b", r"\bsalaries\b", r"\bsalary\b", r"\binterviews?\b",
            r"\bquestions?\b", r"\bhow to\b", r"\btop\b", r"\bbest\b", r"\broadmaps?\b",
            r"\btutorials?\b", r"\bcourses?\b", r"\bbecome\b", r"\bpaths?\b", r"\bscope\b",
            r"\bresumes?\b", r"\bjobs?\b", r"\bcomplete\b", r"\bbeginners?\b", r"\bsyllabus\b",
            r"\bcareers?\b", r"\bhiring\b", r"\bvs\b", r"\bversus\b"
        ]
        for pattern in noise_words:
            t = re.sub(pattern, "", t)

        # Remove extra whitespace after noise word stripping
        t = " ".join(t.split())

        if not t:
            return None

        # General abbreviation expansion
        for pattern, replacement in cls.ABBREVIATIONS.items():
            t = re.sub(pattern, replacement.lower(), t)

        # Standard spacing/prefix normalization
        t = re.sub(r"\bfront[\s\-]+end\b", "frontend", t)
        t = re.sub(r"\bback[\s\-]+end\b", "backend", t)
        t = re.sub(r"\bfull[\s\-]+stack\b", "fullstack", t)

        t = " ".join(t.split())
        if not t:
            return None

        # Capitalize to Title Case nicely
        words = t.split()
        capitalized_words = []
        for w in words:
            # Keep certain acronyms fully uppercase (like UI, UX, QA, CA, HR, BI, SRE, REST, API, OOP)
            if w.upper() in {"UI", "UX", "QA", "CA", "HR", "BI", "SRE", "REST", "API", "OOP", "IT", "MERN", "MEAN", "LAMP"}:
                capitalized_words.append(w.upper())
            else:
                # Handle special casing like C++ or C#
                if w.lower() == "c++":
                    capitalized_words.append("C++")
                elif w.lower() == "c#":
                    capitalized_words.append("C#")
                elif w.lower() == ".net":
                    capitalized_words.append(".NET")
                else:
                    capitalized_words.append(w.capitalize())

        canonical_name = " ".join(capitalized_words)
        return canonical_name

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
        return False
