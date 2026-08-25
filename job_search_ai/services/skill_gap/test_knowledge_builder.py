# -*- coding: utf-8 -*-
import unittest
import frappe
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from job_search_ai.services.skill_gap.knowledge_builder import SkillKnowledgeBuilder
from job_search_ai.services.skill_gap.skill_embedding_index import SkillResolution

class TestSkillKnowledgeBuilder(unittest.TestCase):
    def setUp(self):
        # Clean up database state for test runs
        frappe.db.delete("Unknown Skill")
        frappe.db.delete("Skill Alias")
        test_skills = [
            "Java", "Python", "Rust", "StaleSkillResolved", "NewSkillWithCol",
            "LangChain", "Django", "EmptyAliasSkill", "DupAliasSkill",
            "AliasMatchCanonicalSkill", "InvalidRelSkill", "SelfRefSkill"
        ]
        frappe.db.delete("Skill Master", {"category": "Auto-learned"})
        frappe.db.delete("Skill Master", {"name": ["in", test_skills]})
        frappe.db.delete("Skill Relationship", {"from_skill": ["in", test_skills]})
        frappe.db.delete("Skill Relationship", {"to_skill": ["in", test_skills]})
        frappe.db.delete("Skill Relationship", {"source_name": "SkillKnowledgeBuilder"})

    def tearDown(self):
        pass

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_learn_new_skill_high_confidence(self, mock_resolve, mock_execute):
        # Setup mock resolver to say skill is unknown
        mock_resolve.return_value = SkillResolution(
            input_skill="langchain",
            normalized_skill="langchain",
            canonical_skill=None,
            stage="unknown",
            confidence_band="unknown",
            score=0.0,
            accepted=False,
            fallback_reason="not_found",
            candidates=[]
        )

        # Setup mock response for a high-confidence new skill.
        # Python exists, but Rust does NOT exist in the Skill Master.
        mock_response = {
            "canonical_skill": "LangChain",
            "new_skill": True,
            "aliases": ["langchain-python", "langchainjs"],
            "relationships": [
                {
                    "to_skill": "Python",
                    "relation_type": "Prerequisite",
                    "confidence": 0.95
                },
                {
                    "to_skill": "Rust",
                    "relation_type": "Related",
                    "confidence": 0.88
                }
            ],
            "confidence": 0.96
        }
        mock_execute.return_value = json.dumps(mock_response)

        # Python must exist in Skill Master as a prerequisite target
        if not frappe.db.exists("Skill Master", "Python"):
            frappe.get_doc({
                "doctype": "Skill Master",
                "skill_name": "Python",
                "active": 1
            }).insert(ignore_permissions=True)

        # Rust must NOT exist in Skill Master
        if frappe.db.exists("Skill Master", "Rust"):
            frappe.db.delete("Skill Master", {"name": "Rust"})

        builder = SkillKnowledgeBuilder()
        # Mock embedding sync to avoid Qdrant calls
        builder.sync_skill = MagicMock()

        success = builder.learn_skill("langchain", source="Test")
        self.assertTrue(success)

        # Verify Skill Master is created for LangChain
        self.assertTrue(frappe.db.exists("Skill Master", "LangChain"))
        master_doc = frappe.get_doc("Skill Master", "LangChain")
        aliases = [row.alias for row in master_doc.aliases]
        self.assertIn("langchain-python", aliases)

        # Verify Skill Master is NOT created for Rust
        self.assertFalse(frappe.db.exists("Skill Master", "Rust"))

        # Verify Skill Relationship is created for Python (which exists)
        self.assertTrue(frappe.db.exists("Skill Relationship", {
            "from_skill": "LangChain",
            "to_skill": "Python",
            "relation_type": "Prerequisite"
        }))

        # Verify Skill Relationship is NOT created for Rust (which does not exist)
        self.assertFalse(frappe.db.exists("Skill Relationship", {
            "from_skill": "LangChain",
            "to_skill": "Rust"
        }))

        # Verify Rust is staged in Unknown Skill as Pending
        self.assertTrue(frappe.db.exists("Unknown Skill", "rust"))
        rust_status = frappe.db.get_value("Unknown Skill", "rust", "status")
        self.assertEqual(rust_status, "Pending")

        # Verify Unknown Skill record status for langchain
        self.assertTrue(frappe.db.exists("Unknown Skill", "langchain"))
        status = frappe.db.get_value("Unknown Skill", "langchain", "status")
        self.assertEqual(status, "Learned")

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_learn_skill_low_confidence(self, mock_resolve, mock_execute):
        # Setup mock resolver to say skill is unknown
        mock_resolve.return_value = SkillResolution(
            input_skill="UnknownTechXYZ",
            normalized_skill="UnknownTechXYZ",
            canonical_skill=None,
            stage="unknown",
            confidence_band="unknown",
            score=0.0,
            accepted=False,
            fallback_reason="not_found",
            candidates=[]
        )

        # Setup mock response for low-confidence response
        mock_response = {
            "canonical_skill": "UnknownTechXYZ",
            "new_skill": True,
            "aliases": [],
            "relationships": [],
            "confidence": 0.50
        }
        mock_execute.return_value = json.dumps(mock_response)

        builder = SkillKnowledgeBuilder()
        success = builder.learn_skill("UnknownTechXYZ", source="Test")
        self.assertFalse(success)

        # Verify Skill Master is NOT created
        self.assertFalse(frappe.db.exists("Skill Master", "UnknownTechXYZ"))

        # Verify Unknown Skill record is created with Pending status
        self.assertTrue(frappe.db.exists("Unknown Skill", "unknowntechxyz"))
        status = frappe.db.get_value("Unknown Skill", "unknowntechxyz", "status")
        self.assertEqual(status, "Pending")
        confidence = frappe.db.get_value("Unknown Skill", "unknowntechxyz", "confidence")
        self.assertEqual(confidence, 0.50)

    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_prevent_concurrent_calls(self, mock_resolve):
        # Setup mock resolver to say skill is unknown
        mock_resolve.return_value = SkillResolution(
            input_skill="ConcurrentSkill",
            normalized_skill="ConcurrentSkill",
            canonical_skill=None,
            stage="unknown",
            confidence_band="unknown",
            score=0.0,
            accepted=False,
            fallback_reason="not_found",
            candidates=[]
        )

        # Insert a pre-existing "Pending" lock record in Unknown Skill (recent modified time)
        frappe.get_doc({
            "doctype": "Unknown Skill",
            "normalized_key": "concurrentskill",
            "raw_text": "ConcurrentSkill",
            "normalized_text": "ConcurrentSkill",
            "status": "Pending",
            "confidence": 0.0,
            "source": "TestLock"
        }).insert(ignore_permissions=True)

        builder = SkillKnowledgeBuilder()
        builder._execute_llm = MagicMock()

        # Try to learn the same skill
        success = builder.learn_skill("ConcurrentSkill", source="Test")
        # Should return False immediately without calling the LLM
        self.assertFalse(success)
        builder._execute_llm.assert_not_called()

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_stale_lock_recovery(self, mock_resolve, mock_execute):
        mock_resolve.return_value = SkillResolution(
            input_skill="StaleSkill",
            normalized_skill="StaleSkill",
            canonical_skill=None,
            stage="unknown",
            confidence_band="unknown",
            score=0.0,
            accepted=False,
            fallback_reason="not_found",
            candidates=[]
        )

        # Insert a pre-existing stale Pending record (modified > 15 mins ago)
        doc = frappe.get_doc({
            "doctype": "Unknown Skill",
            "normalized_key": "staleskill",
            "raw_text": "StaleSkill",
            "normalized_text": "staleskill",
            "status": "Pending",
            "confidence": 0.0,
            "source": "TestLock"
        }).insert(ignore_permissions=True)
        # Manually backdate the modified field using raw SQL to bypass Frappe ORM override
        frappe.db.sql("UPDATE `tabUnknown Skill` SET modified = %s WHERE name = 'staleskill'", (datetime.now() - timedelta(minutes=20),))
        frappe.db.commit()

        mock_response = {
            "canonical_skill": "StaleSkillResolved",
            "new_skill": True,
            "aliases": [],
            "relationships": [],
            "confidence": 0.95
        }
        mock_execute.return_value = json.dumps(mock_response)

        builder = SkillKnowledgeBuilder()
        builder.sync_skill = MagicMock()
        
        success = builder.learn_skill("StaleSkill", source="Test")
        # Should proceed to execute and return True
        self.assertTrue(success)
        self.assertTrue(frappe.db.exists("Skill Master", "StaleSkillResolved"))

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_global_alias_collision(self, mock_resolve, mock_execute):
        mock_resolve.return_value = SkillResolution(
            input_skill="NewSkillWithCol",
            normalized_skill="NewSkillWithCol",
            canonical_skill=None,
            stage="unknown",
            confidence_band="unknown",
            score=0.0,
            accepted=False,
            fallback_reason="not_found",
            candidates=[]
        )

        # Pre-exist Python canonical and Java alias
        if not frappe.db.exists("Skill Master", "Python"):
            frappe.get_doc({
                "doctype": "Skill Master",
                "skill_name": "Python",
                "active": 1
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Skill Master", "Java"):
            j_doc = frappe.get_doc({
                "doctype": "Skill Master",
                "skill_name": "Java",
                "active": 1
            }).insert(ignore_permissions=True)
            j_doc.append("aliases", {"alias": "JavaAlias"})
            j_doc.save(ignore_permissions=True)
            frappe.db.commit()

        # LLM response suggests Python (exists in Skill Master) and JavaAlias (exists as alias on Java)
        mock_response = {
            "canonical_skill": "NewSkillWithCol",
            "new_skill": True,
            "aliases": ["Python", "JavaAlias", "UniqueNewAlias"],
            "relationships": [],
            "confidence": 0.95
        }
        mock_execute.return_value = json.dumps(mock_response)

        builder = SkillKnowledgeBuilder()
        builder.sync_skill = MagicMock()

        success = builder.learn_skill("NewSkillWithCol", source="Test")
        self.assertTrue(success)

        # Verify collision aliases Python and JavaAlias were not added
        master_doc = frappe.get_doc("Skill Master", "NewSkillWithCol")
        aliases = [row.alias for row in master_doc.aliases]
        self.assertNotIn("Python", aliases)
        self.assertNotIn("JavaAlias", aliases)
        self.assertIn("UniqueNewAlias", aliases)

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_learn_skill_error_handling(self, mock_resolve, mock_execute):
        # Setup mock resolver to say skill is unknown
        mock_resolve.return_value = SkillResolution(
            input_skill="BrokenSkill",
            normalized_skill="BrokenSkill",
            canonical_skill=None,
            stage="unknown",
            confidence_band="unknown",
            score=0.0,
            accepted=False,
            fallback_reason="not_found",
            candidates=[]
        )

        # Setup LLM execution to raise an exception
        mock_execute.side_effect = Exception("Connection Timeout")

        builder = SkillKnowledgeBuilder()
        success = builder.learn_skill("BrokenSkill", source="Test")
        self.assertFalse(success)

        # Verify Unknown Skill record is created with Error status
        self.assertTrue(frappe.db.exists("Unknown Skill", "brokenskill"))
        status = frappe.db.get_value("Unknown Skill", "brokenskill", "status")
        self.assertEqual(status, "Error")

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_validator_rejects_empty_aliases(self, mock_resolve, mock_execute):
        mock_resolve.return_value = SkillResolution("EmptyAliasSkill", "EmptyAliasSkill", None, "unknown", "unknown", 0.0, False, "not_found", [])
        mock_response = {
            "canonical_skill": "EmptyAliasSkill",
            "new_skill": True,
            "aliases": ["ValidAlias", ""],
            "relationships": [],
            "confidence": 0.95
        }
        mock_execute.return_value = json.dumps(mock_response)
        builder = SkillKnowledgeBuilder()
        success = builder.learn_skill("EmptyAliasSkill", source="Test")
        self.assertFalse(success)
        status = frappe.db.get_value("Unknown Skill", "emptyaliasskill", "status")
        self.assertEqual(status, "Error")
        llm_response = frappe.db.get_value("Unknown Skill", "emptyaliasskill", "llm_response")
        self.assertIn("Alias list contains empty or invalid strings", llm_response)

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_validator_rejects_duplicate_aliases(self, mock_resolve, mock_execute):
        mock_resolve.return_value = SkillResolution("DupAliasSkill", "DupAliasSkill", None, "unknown", "unknown", 0.0, False, "not_found", [])
        mock_response = {
            "canonical_skill": "DupAliasSkill",
            "new_skill": True,
            "aliases": ["AliasA", "aliasA"],
            "relationships": [],
            "confidence": 0.95
        }
        mock_execute.return_value = json.dumps(mock_response)
        builder = SkillKnowledgeBuilder()
        success = builder.learn_skill("DupAliasSkill", source="Test")
        self.assertFalse(success)
        status = frappe.db.get_value("Unknown Skill", "dupaliasskill", "status")
        self.assertEqual(status, "Error")
        llm_response = frappe.db.get_value("Unknown Skill", "dupaliasskill", "llm_response")
        self.assertIn("Duplicate aliases found in response", llm_response)

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_validator_rejects_alias_matching_canonical(self, mock_resolve, mock_execute):
        mock_resolve.return_value = SkillResolution("AliasMatchCanonicalSkill", "AliasMatchCanonicalSkill", None, "unknown", "unknown", 0.0, False, "not_found", [])
        mock_response = {
            "canonical_skill": "AliasMatchCanonicalSkill",
            "new_skill": True,
            "aliases": ["aliasmatchcanonicalskill"],
            "relationships": [],
            "confidence": 0.95
        }
        mock_execute.return_value = json.dumps(mock_response)
        builder = SkillKnowledgeBuilder()
        success = builder.learn_skill("AliasMatchCanonicalSkill", source="Test")
        self.assertFalse(success)
        status = frappe.db.get_value("Unknown Skill", "aliasmatchcanonicalskill", "status")
        self.assertEqual(status, "Error")
        llm_response = frappe.db.get_value("Unknown Skill", "aliasmatchcanonicalskill", "llm_response")
        self.assertIn("Alias cannot be identical to canonical skill name", llm_response)

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_validator_rejects_invalid_relation_types(self, mock_resolve, mock_execute):
        mock_resolve.return_value = SkillResolution("InvalidRelSkill", "InvalidRelSkill", None, "unknown", "unknown", 0.0, False, "not_found", [])
        mock_response = {
            "canonical_skill": "InvalidRelSkill",
            "new_skill": True,
            "aliases": [],
            "relationships": [
                {
                    "to_skill": "Python",
                    "relation_type": "SuperPrerequisite",
                    "confidence": 0.9
                }
            ],
            "confidence": 0.95
        }
        mock_execute.return_value = json.dumps(mock_response)
        builder = SkillKnowledgeBuilder()
        success = builder.learn_skill("InvalidRelSkill", source="Test")
        self.assertFalse(success)
        status = frappe.db.get_value("Unknown Skill", "invalidrelskill", "status")
        self.assertEqual(status, "Error")
        llm_response = frappe.db.get_value("Unknown Skill", "invalidrelskill", "llm_response")
        self.assertIn("Invalid relationship type", llm_response)

    @patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm")
    @patch("job_search_ai.services.skill_gap.skill_embedding_index.SkillEmbeddingResolver.resolve")
    def test_validator_rejects_self_references(self, mock_resolve, mock_execute):
        mock_resolve.return_value = SkillResolution("SelfRefSkill", "SelfRefSkill", None, "unknown", "unknown", 0.0, False, "not_found", [])
        mock_response = {
            "canonical_skill": "SelfRefSkill",
            "new_skill": True,
            "aliases": [],
            "relationships": [
                {
                    "to_skill": "selfrefskill",
                    "relation_type": "Contains",
                    "confidence": 0.9
                }
            ],
            "confidence": 0.95
        }
        mock_execute.return_value = json.dumps(mock_response)
        builder = SkillKnowledgeBuilder()
        success = builder.learn_skill("SelfRefSkill", source="Test")
        self.assertFalse(success)
        status = frappe.db.get_value("Unknown Skill", "selfrefskill", "status")
        self.assertEqual(status, "Error")
        llm_response = frappe.db.get_value("Unknown Skill", "selfrefskill", "llm_response")
        self.assertIn("Self-referential relationships are not allowed", llm_response)

    def test_validator_rejects_circular_relationships(self):
        # We need pre-existing Python and Django skills in the database
        for sk in ["Python", "Django"]:
            if not frappe.db.exists("Skill Master", sk):
                frappe.get_doc({
                    "doctype": "Skill Master",
                    "skill_name": sk,
                    "active": 1
                }).insert(ignore_permissions=True)

        # Insert a relationship from Python to Django in the database
        if not frappe.db.exists("Skill Relationship", {"from_skill": "Python", "to_skill": "Django", "relation_type": "Contains"}):
            frappe.get_doc({
                "doctype": "Skill Relationship",
                "from_skill": "Python",
                "relation_type": "Contains",
                "to_skill": "Django",
                "confidence": 1.0,
                "source_type": "Manual",
                "is_trusted_source": 1,
                "status": "Approved",
                "active": 1
            }).insert(ignore_permissions=True)

        # Now, the LLM proposes that Django --Prerequisite--> Python (creating Python -> Django -> Python cycle)
        mock_response = {
            "canonical_skill": "Django",
            "new_skill": False,
            "aliases": [],
            "relationships": [
                {
                    "to_skill": "Python",
                    "relation_type": "Prerequisite",
                    "confidence": 0.9
                }
            ],
            "confidence": 0.95
        }

        builder = SkillKnowledgeBuilder()
        with self.assertRaises(ValueError) as ctx:
            builder._validate_llm_payload(mock_response, "Django")
        self.assertIn("Circular reference detected in relationship graph", str(ctx.exception))

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSkillKnowledgeBuilder)
    runner = unittest.TextTestRunner()
    runner.run(suite)

def print_relationship_cache():
    import frappe
    
    records = frappe.get_all(
        "Skill Relationship",
        fields=["name", "from_skill", "relation_type", "to_skill", "active", "status", "confidence", "is_trusted_source"]
    )
    print("--- ALL SKILL RELATIONSHIPS ---")
    for r in records:
        print("  {} --({})--> {}, active={}, status={}, confidence={}, is_trusted={}".format(
            r.from_skill, r.relation_type, r.to_skill, r.active, r.status, r.confidence, r.is_trusted_source
        ))
