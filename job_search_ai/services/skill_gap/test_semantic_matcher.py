"""
Unit tests for the semantic skill matching layer.
Run via:
python -m unittest job_search_ai/services/skill_gap/test_semantic_matcher.py
"""

import unittest

from job_search_ai.services.skill_gap.analyzer import SkillGapAnalyzer
from job_search_ai.services.skill_gap.matcher import SemanticSkillMatcher
from job_search_ai.services.skill_gap.schemas import StudentSkillItem


class TestSemanticSkillMatcher(unittest.TestCase):

    def test_fingerprint_matches_common_skill_variants(self):
        matcher = SemanticSkillMatcher()

        canonical = matcher.canonicalize_inputs(
            student_skills=[
                StudentSkillItem("HTML"),
                StudentSkillItem("CSS"),
                StudentSkillItem("JS Programming"),
                StudentSkillItem("React Framework"),
                StudentSkillItem("NodeJS Development"),
            ],
            foundation_skills=["HTML", "CSS", "JavaScript", "React", "Node.js"],
            core_domain_skills=[],
            industry_skills=[],
            emerging_skills=[],
        )

        self.assertEqual(
            [item.skill for item in canonical.student_skills],
            ["HTML", "CSS", "JavaScript", "React", "Node.js"],
        )
        self.assertEqual(canonical.foundation_skills, ["HTML", "CSS", "JavaScript", "React", "Node.js"])
        self.assertEqual({match.stage for match in canonical.matches}, {"exact", "semantic_fingerprint"})

    def test_semantic_inputs_make_analyzer_match_canonical_skills(self):
        matcher = SemanticSkillMatcher()
        canonical = matcher.canonicalize_inputs(
            student_skills=[StudentSkillItem("Python Programming", "Advanced")],
            foundation_skills=["Python"],
            core_domain_skills=[],
            industry_skills=[],
            emerging_skills=[],
        )

        report = SkillGapAnalyzer().analyze(
            student_identifier="student@example.com",
            career_title="Python Developer",
            student_skills=canonical.student_skills,
            foundation_skills=canonical.foundation_skills,
            core_domain_skills=[],
            industry_skills=[],
            emerging_skills=[],
        )

        self.assertEqual(report.matched_skills, ["Python"])
        self.assertEqual(report.missing_foundation, [])
        self.assertEqual(report.readiness_score, 100.0)



    def test_java_does_not_match_javascript(self):
        matcher = SemanticSkillMatcher()
        matches = matcher.match_skills(["Java"], ["JavaScript"])
        self.assertEqual(matches, [])

    def test_embedding_match_is_used_after_exact_and_fingerprint(self):
        vectors = {
            "Data Visualization": [1.0, 0.0],
            "Charting": [0.95, 0.05],
        }
        calls = []

        def embed(skill):
            calls.append(skill)
            return vectors[skill]

        matcher = SemanticSkillMatcher(embedding_provider=embed, embedding_match_threshold=0.90)
        matches = matcher.match_skills(["Charting"], ["Data Visualization"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].stage, "semantic_embedding")
        self.assertGreaterEqual(matches[0].score, 0.90)
        self.assertEqual(sorted(calls), ["Charting", "Data Visualization"])

    def test_llm_fallback_only_runs_for_embedding_inconclusive_pairs(self):
        vectors = {
            "Python Scripting": [1.0, 0.0],
            "Python Automation": [0.75, 0.25],
        }
        llm_calls = []

        def embed(skill):
            return vectors[skill]

        def decide(left, right):
            llm_calls.append((left, right))
            return True

        matcher = SemanticSkillMatcher(
            embedding_provider=embed,
            llm_decider=decide,
            embedding_match_threshold=0.99,
            embedding_inconclusive_threshold=0.80,
        )
        matches = matcher.match_skills(["Python Automation"], ["Python Scripting"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].stage, "llm_fallback")
        self.assertEqual(llm_calls, [("Python Automation", "Python Scripting")])

    def test_regression_false_positive_pairs_do_not_match_without_index(self):
        matcher = SemanticSkillMatcher()
        pairs = [
            ("React", "React Native"),
            ("SQL", "NoSQL"),
            ("MongoDB", "MySQL"),
            ("TensorFlow", "TensorRT"),
        ]

        for student_skill, required_skill in pairs:
            with self.subTest(student_skill=student_skill, required_skill=required_skill):
                self.assertEqual(matcher.match_skills([student_skill], [required_skill]), [])


if __name__ == "__main__":
    unittest.main()
