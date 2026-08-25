# -*- coding: utf-8 -*-
# job_search_ai/services/skill_gap/test_relationship.py

import unittest
import frappe
from job_search_ai.services.skill_gap.schemas import StudentSkillItem
from job_search_ai.services.skill_gap.normalizer import invalidate_normalization_cache
from job_search_ai.services.skill_gap.relationship import (
    expand_skill_relations,
    invalidate_relationship_cache,
    RELATION_ALIAS,
    RELATION_CONTAINS,
    RELATION_RELATED,
)
from job_search_ai.services.skill_gap.matcher import SemanticSkillMatcher


class TestSkillRelationship(unittest.TestCase):

    def setUp(self):
        # Seed Skills
        self.skills = [
            "DSA", "Data Structures", "Algorithms",
            "AWS", "EC2", "Lambda",
            "Machine Learning", "Supervised Learning", "Regression",
            "ReactJS", "React", "Next.js",
            "Docker", "Kubernetes",
            "Probability", "Probability Theory"
        ]

        # Clean existing test entries to prevent duplicates
        frappe.db.delete("Skill Relationship", {"from_skill": ["in", self.skills]})
        frappe.db.delete("Skill Relationship", {"to_skill": ["in", self.skills]})
        frappe.db.delete("Skill Alias", {"alias": ["in", self.skills]})
        frappe.db.delete("Skill Master", {"skill_name": ["in", self.skills]})

        # Create Skill Masters
        for skill in self.skills:
            doc = frappe.get_doc({
                "doctype": "Skill Master",
                "skill_name": skill,
                "active": 1
            })
            doc.insert(ignore_permissions=True)

        # Create Skill Relationships
        self.relationships = [
            ("DSA", RELATION_CONTAINS, "Data Structures"),
            ("DSA", RELATION_CONTAINS, "Algorithms"),
            ("AWS", RELATION_CONTAINS, "EC2"),
            ("AWS", RELATION_CONTAINS, "Lambda"),
            ("Machine Learning", RELATION_CONTAINS, "Supervised Learning"),
            ("Machine Learning", RELATION_CONTAINS, "Regression"),
            ("ReactJS", RELATION_ALIAS, "React"),
            ("React", RELATION_RELATED, "Next.js"),
            ("Docker", RELATION_RELATED, "Kubernetes"),
            ("Probability", RELATION_ALIAS, "Probability Theory"),
        ]

        for from_skill, rel_type, to_skill in self.relationships:
            doc = frappe.get_doc({
                "doctype": "Skill Relationship",
                "from_skill": from_skill,
                "relation_type": rel_type,
                "to_skill": to_skill,
                "confidence": 1.0,
                "source_type": "Manual",
                "is_trusted_source": 1,
                "status": "Approved",
                "active": 1
            })
            doc.insert(ignore_permissions=True)

        invalidate_normalization_cache()
        invalidate_relationship_cache()

    def tearDown(self):
        # Cleanup Relationships and Skills
        frappe.db.delete("Skill Relationship", {"from_skill": ["in", self.skills]})
        frappe.db.delete("Skill Relationship", {"to_skill": ["in", self.skills]})
        frappe.db.delete("Skill Alias", {"alias": ["in", self.skills]})
        frappe.db.delete("Skill Master", {"skill_name": ["in", self.skills]})
        invalidate_normalization_cache()
        invalidate_relationship_cache()

    def test_contains_expansion(self):
        # DSA contains Data Structures and Algorithms
        res = expand_skill_relations("DSA")
        self.assertIn("DSA", res)
        self.assertIn("Data Structures", res)
        self.assertIn("Algorithms", res)

        # AWS contains EC2 and Lambda
        res = expand_skill_relations("AWS")
        self.assertIn("AWS", res)
        self.assertIn("EC2", res)
        self.assertIn("Lambda", res)

        # Machine Learning contains Supervised Learning and Regression
        res = expand_skill_relations("Machine Learning")
        self.assertIn("Machine Learning", res)
        self.assertIn("Supervised Learning", res)
        self.assertIn("Regression", res)

    def test_alias_expansion(self):
        # ReactJS and React are aliases (bidirectional)
        res = expand_skill_relations("ReactJS")
        self.assertIn("ReactJS", res)
        self.assertIn("React", res)

        res2 = expand_skill_relations("React")
        self.assertIn("React", res2)
        self.assertIn("ReactJS", res2)

        # Probability and Probability Theory are aliases
        res3 = expand_skill_relations("Probability")
        self.assertIn("Probability", res3)
        self.assertIn("Probability Theory", res3)

    def test_related_and_other_no_expansion(self):
        # Related and Prerequisite should NOT match/expand automatically
        res = expand_skill_relations("React")
        self.assertNotIn("Next.js", res)

        res2 = expand_skill_relations("Docker")
        self.assertNotIn("Kubernetes", res2)

    def test_status_filtering(self):
        # Create a Pending and a Rejected relationship
        frappe.get_doc({
            "doctype": "Skill Relationship",
            "from_skill": "AWS",
            "relation_type": RELATION_CONTAINS,
            "to_skill": "Kubernetes",
            "confidence": 0.8,
            "source_type": "LLM",
            "source_name": "GPT-4",
            "is_trusted_source": 0,
            "status": "Pending",
            "active": 1
        }).insert(ignore_permissions=True)

        frappe.get_doc({
            "doctype": "Skill Relationship",
            "from_skill": "AWS",
            "relation_type": RELATION_CONTAINS,
            "to_skill": "Docker",
            "confidence": 0.5,
            "source_type": "LLM",
            "source_name": "GPT-4",
            "is_trusted_source": 0,
            "status": "Rejected",
            "active": 1
        }).insert(ignore_permissions=True)

        frappe.db.commit()
        invalidate_relationship_cache()

        # AWS should NOT expand to Kubernetes or Docker because status is not Approved
        res = expand_skill_relations("AWS")
        self.assertNotIn("Kubernetes", res)
        self.assertNotIn("Docker", res)

    def test_cycle_detection(self):
        # Create cycle: Docker -> contains -> Kubernetes, and Kubernetes -> contains -> Docker
        frappe.get_doc({
            "doctype": "Skill Relationship",
            "from_skill": "Docker",
            "relation_type": RELATION_CONTAINS,
            "to_skill": "Kubernetes",
            "confidence": 1.0,
            "source_type": "Manual",
            "is_trusted_source": 1,
            "status": "Approved",
            "active": 1
        }).insert(ignore_permissions=True)

        frappe.get_doc({
            "doctype": "Skill Relationship",
            "from_skill": "Kubernetes",
            "relation_type": RELATION_CONTAINS,
            "to_skill": "Docker",
            "confidence": 1.0,
            "source_type": "Manual",
            "is_trusted_source": 1,
            "status": "Approved",
            "active": 1
        }).insert(ignore_permissions=True)

        frappe.db.commit()
        invalidate_relationship_cache()

        # Capture warnings
        with self.assertLogs("job_search_ai.services.skill_gap.relationship", level="WARNING") as log:
            res = expand_skill_relations("Docker")
            # Verify cycle warning was logged
            self.assertTrue(any("cycle detected in graph path" in message for message in log.output))

        self.assertIn("Docker", res)
        self.assertIn("Kubernetes", res)

    def test_confidence_threshold(self):
        """
        Trust is per-record (is_trusted_source flag), not per source_type.
        - is_trusted_source=1 → always loaded regardless of confidence.
        - is_trusted_source=0 → only loaded if confidence >= threshold.
        This means ESCO (Imported) can be marked trusted, while a raw LLM
        suggestion is not, even if both share source_type='Imported'.
        """
        orig_get_single_value = frappe.db.get_single_value
        orig_get_meta = frappe.get_meta

        frappe.db.get_single_value = (
            lambda doctype, fieldname: 0.8
            if fieldname == "skill_relationship_confidence_threshold"
            else orig_get_single_value(doctype, fieldname)
        )

        def mock_get_meta(doctype):
            meta = orig_get_meta(doctype)
            if doctype == "Job Search AI Settings":
                orig_has_field = meta.has_field
                meta.has_field = lambda fieldname: True if fieldname == "skill_relationship_confidence_threshold" else orig_has_field(fieldname)
            return meta
        frappe.get_meta = mock_get_meta

        try:
            # LLM suggestion, NOT trusted, confidence 0.9 >= 0.8 — should be included
            frappe.get_doc({
                "doctype": "Skill Relationship",
                "from_skill": "AWS",
                "relation_type": RELATION_CONTAINS,
                "to_skill": "Kubernetes",
                "confidence": 0.9,
                "source_type": "LLM",
                "source_name": "GPT-4",
                "is_trusted_source": 0,
                "status": "Approved",
                "active": 1
            }).insert(ignore_permissions=True)

            # LLM suggestion, NOT trusted, confidence 0.5 < 0.8 — should be excluded
            frappe.get_doc({
                "doctype": "Skill Relationship",
                "from_skill": "AWS",
                "relation_type": RELATION_CONTAINS,
                "to_skill": "Docker",
                "confidence": 0.5,
                "source_type": "LLM",
                "source_name": "GPT-4",
                "is_trusted_source": 0,
                "status": "Approved",
                "active": 1
            }).insert(ignore_permissions=True)

            # ESCO import, IS trusted, confidence 0.1 < 0.8 — should be included anyway
            frappe.get_doc({
                "doctype": "Skill Relationship",
                "from_skill": "AWS",
                "relation_type": RELATION_CONTAINS,
                "to_skill": "Lambda",
                "confidence": 0.1,
                "source_type": "Imported",
                "source_name": "ESCO",
                "is_trusted_source": 1,
                "status": "Approved",
                "active": 1
            }).insert(ignore_permissions=True)

            frappe.db.commit()
            invalidate_relationship_cache()

            res = expand_skill_relations("AWS")
            # Kubernetes: LLM untrusted 0.9 >= 0.8 — included
            self.assertIn("Kubernetes", res)
            # Docker: LLM untrusted 0.5 < 0.8 — excluded
            self.assertNotIn("Docker", res)
            # Lambda: ESCO trusted 0.1 — included regardless of confidence
            self.assertIn("Lambda", res)

        finally:
            frappe.db.get_single_value = orig_get_single_value
            frappe.get_meta = orig_get_meta

    def test_proficiency_level_preservation(self):
        matcher = SemanticSkillMatcher()

        # Test Case 1: Student has DSA (Advanced)
        student_skills = [
            StudentSkillItem(skill="DSA", current_level="Advanced")
        ]
        expanded = matcher._expand_student_skills(student_skills)
        
        # Verify expanded list contains all children with parent's level
        expanded_map = {item.skill: item.current_level for item in expanded}
        self.assertEqual(expanded_map.get("DSA"), "Advanced")
        self.assertEqual(expanded_map.get("Data Structures"), "Advanced")
        self.assertEqual(expanded_map.get("Algorithms"), "Advanced")

        # Test Case 2: Student has DSA (Advanced) and Data Structures (Beginner)
        student_skills_2 = [
            StudentSkillItem(skill="DSA", current_level="Advanced"),
            StudentSkillItem(skill="Data Structures", current_level="Beginner")
        ]
        expanded_2 = matcher._expand_student_skills(student_skills_2)
        
        # Verify highest level (Advanced) is preserved for Data Structures
        expanded_map_2 = {item.skill: item.current_level for item in expanded_2}
        self.assertEqual(expanded_map_2.get("Data Structures"), "Advanced")


def run_tests():
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSkillRelationship)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        import sys
        sys.exit(1)
