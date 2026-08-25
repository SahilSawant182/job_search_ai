"""
Unit tests for Skill Normalizer atomic parsing, dangling word removal, and alias canonicalization.
Run via:
pytest job_search_ai/services/skill_gap/test_skill_normalizer.py
or python -m unittest job_search_ai/services/skill_gap/test_skill_normalizer.py
"""

import unittest
from job_search_ai.services.skill_gap.normalizer import (
    clean_dangling_words,
    parse_skill_string,
    get_skill_key,
    normalize_skill,
)


class TestSkillNormalizer(unittest.TestCase):

    def test_dangling_words_removal(self):
        self.assertEqual(clean_dangling_words("and DynamoDB"), "DynamoDB")
        self.assertEqual(clean_dangling_words("and Cosmos DB"), "Cosmos DB")
        self.assertEqual(clean_dangling_words("and Hive"), "Hive")
        self.assertEqual(clean_dangling_words("GitHub for"), "GitHub")
        self.assertEqual(clean_dangling_words("using React with Redux"), "React with Redux")

    def test_alias_canonicalization(self):
        self.assertEqual(get_skill_key("NLP"), get_skill_key("Natural Language Processing"))
        self.assertEqual(get_skill_key("AutoML"), get_skill_key("Automated Machine Learning"))
        self.assertEqual(get_skill_key("IoT"), get_skill_key("Internet of Things Integration"))
        self.assertEqual(get_skill_key("PyTorch Fundamentals"), get_skill_key("PyTorch"))

    def test_incomplete_concept_resolutions(self):
        self.assertEqual(normalize_skill("Structures"), "Data Structures")
        self.assertEqual(normalize_skill("Supervised"), "Supervised Learning")
        self.assertEqual(normalize_skill("Unsupervised"), "Unsupervised Learning")
        self.assertEqual(normalize_skill("Statistics Fundamentals"), "Statistics")

    def test_deduplication_and_atomic_decomposition(self):
        input_skills = [
            "GitHub for",
            "and DynamoDB",
            "and Cosmos DB",
            "and Hive",
            "Natural Language Processing",
            "NLP",
            "AutoML",
            "Automated Machine Learning",
            "Internet of Things Integration",
            "IoT",
            "PyTorch Fundamentals",
        ]
        parsed = parse_skill_string(input_skills)
        expected = [
            "GitHub",
            "DynamoDB",
            "Cosmos DB",
            "Hive",
            "Natural Language Processing",
            "Automated Machine Learning",
            "Internet of Things",
            "PyTorch",
        ]
        self.assertEqual(parsed, expected)


if __name__ == "__main__":
    unittest.main()
