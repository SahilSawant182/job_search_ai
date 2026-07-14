# -*- coding: utf-8 -*-
import re

class ContentCleaner:
    """
    Cleans webpage content to isolate career intelligence.
    Removes cookies, navigation, ads, promos, and footers.
    Retains sections/paragraphs mentioning roles, skills, salaries, and demands.
    """

    # Terms indicating junk/marketing content to reject
    JUNK_PATTERNS = [
        r"cookie", r"privacy policy", r"terms of service", r"all rights reserved",
        r"subscribe to", r"newsletter", r"click here", r"sign up", r"advertisement",
        r"share this", r"related articles", r"read also", r"follow us", r"copyright",
        r"log in", r"create account", r"forgot password", r"search this site",
        r"menu", r"navigation", r"skip to main", r"close menu", r"training courses",
        r"bootcamp", r"get certified", r"discount", r"coupon", r"pricing", r"buy now"
    ]

    # Terms indicating career intelligence to retain
    CAREER_INTELLIGENCE_KEYWORDS = [
        "skill", "tool", "framework", "language", "technology", "hiring", "salary",
        "jobs", "career", "demand", "experience", "role", "qualification", "company",
        "companies", "responsibility", "trend", "industry", "recruit", "market"
    ]

    @staticmethod
    def clean(raw_text: str) -> str:
        """
        Cleans raw markdown or plain text, returning only the paragraphs/lines
        that contain relevant career intelligence.
        """
        if not raw_text:
            return ""

        cleaned_blocks = []
        # Split text into paragraphs or blocks
        blocks = re.split(r'\n\s*\n', raw_text)

        for block in blocks:
            block_clean = block.strip()
            if not block_clean:
                continue

            # 1. Filter out blocks that match junk patterns
            is_junk = False
            for pattern in ContentCleaner.JUNK_PATTERNS:
                if re.search(pattern, block_clean.lower()):
                    is_junk = True
                    break
            if is_junk:
                continue

            # 2. Check if the block contains relevant career keywords or standard technical lists
            has_career_relevance = False
            for keyword in ContentCleaner.CAREER_INTELLIGENCE_KEYWORDS:
                if keyword in block_clean.lower():
                    has_career_relevance = True
                    break

            # 3. Also allow code blocks or bulleted list items that look like tech/skills list
            if not has_career_relevance:
                # If it's a list item starting with * or - and is short (usually a skill or tool name)
                lines = block_clean.split("\n")
                if len(lines) > 1 and all(l.strip().startswith(('*', '-', '•', '1.', '2.', '3.')) for l in lines if l.strip()):
                    has_career_relevance = True

            if has_career_relevance:
                # Do light syntax/formatting cleanup
                # Remove excessive whitespace
                block_clean = re.sub(r'[ \t]+', ' ', block_clean)
                cleaned_blocks.append(block_clean)

        return "\n\n".join(cleaned_blocks)
