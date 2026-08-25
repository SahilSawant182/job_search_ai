"""
Regression tests for Skill Gap Agent Remediations.
Run via:
bench --site devstridenex.quantcloud.in execute job_search_ai.services.skill_gap.test_fixes.run_tests
"""

import unittest
import frappe
import time
import job_search_ai.services.skill_gap.normalizer as norm
from job_search_ai.services.skill_gap.service import SkillGapService
from job_search_ai.services.skill_gap.skill_embedding_index import (
    PersistentSkillEmbeddingCache,
    SkillEmbeddingResolver,
    SkillSearchCandidate,
)

class TestRemediations(unittest.TestCase):

    def setUp(self):
        frappe.db.begin()

    def tearDown(self):
        frappe.db.rollback()

    def test_cache_invalidation_hooks(self):
        # 1. Create a dummy Skill Master and verify it's loaded in cache
        sm_name = "Test Unique Skill XYZ"
        if frappe.db.exists("Skill Master", sm_name):
            frappe.db.delete("Skill Master", {"name": sm_name})
        
        # Invalidate first to clean up
        norm.invalidate_normalization_cache()
        
        doc = frappe.get_doc({
            "doctype": "Skill Master",
            "skill_name": sm_name,
            "active": 1
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        # The cache should contain this new skill key
        self.assertIn(sm_name.lower().strip(), norm._MASTER_CACHE)

        # 2. Update the skill and verify cache updates
        doc.active = 0
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        # Since it's inactive, the cache should no longer contain this skill key
        self.assertNotIn(sm_name.lower().strip(), norm._MASTER_CACHE)

        # Cleanup
        frappe.db.delete("Skill Master", {"name": sm_name})
        frappe.db.commit()

    def test_validation_errors(self):
        service = SkillGapService()
        
        # Test 1: Invalid student raises DoesNotExistError
        with self.assertRaises(frappe.DoesNotExistError):
            service.get_skill_gap_report(student="non_existent_student_123@xyz.com", role="Machine Learning Engineer")

        # Test 2: Invalid role raises DoesNotExistError
        # Create a test student first
        student_id = "test_val_error@example.com"
        college_name = frappe.db.get_value("College", {}, "name") or "Default College"
        
        if not frappe.db.exists("Student", student_id):
            stu = frappe.get_doc({
                "doctype": "Student",
                "first_name": "Test",
                "last_name": "Student",
                "email_id": student_id,
                "college": college_name
            })
            stu.insert(ignore_permissions=True)
            frappe.db.commit()

        with self.assertRaises(frappe.DoesNotExistError):
            service.get_skill_gap_report(student=student_id, role="Non Existent Role ABC")

        # Cleanup student
        frappe.db.delete("Student", {"name": student_id})
        frappe.db.commit()

    def test_upsert_concurrency_cache(self):
        cache = PersistentSkillEmbeddingCache()
        cache_key = "concurrency_test_key"
        
        # Setup clean state in DB
        frappe.db.delete("Skill Embedding Cache", {"skill_key": cache_key})
        frappe.db.commit()

        # Set first time
        cache.set(
            cache_key=cache_key,
            skill_text="Some text",
            vector=[0.1, 0.2, 0.3],
            model="test-model",
            version="1.0",
            text_hash="hash1",
            source="skill_master"
        )
        frappe.db.commit()

        # Set second time (simulating update or concurrent write without raising DuplicateEntryError)
        cache.set(
            cache_key=cache_key,
            skill_text="Some updated text",
            vector=[0.4, 0.5, 0.6],
            model="test-model",
            version="1.0",
            text_hash="hash2",
            source="skill_master"
        )
        frappe.db.commit()

        # Verify values updated
        record = frappe.db.get_value("Skill Embedding Cache", {"skill_key": cache_key}, ["skill_text", "text_hash"], as_dict=True)
        self.assertEqual(record["skill_text"], "Some updated text")
        self.assertEqual(record["text_hash"], "hash2")

        frappe.db.delete("Skill Embedding Cache", {"skill_key": cache_key})
        frappe.db.commit()

    def test_inactive_skill_filtering(self):
        # Setup fake index candidates
        resolver = SkillEmbeddingResolver()
        
        # Let's mock the repository check for a non-existent/deleted skill
        non_existent_skill = "Non Existent Skill Master 999"
        candidates = [
            SkillSearchCandidate(
                skill_id=non_existent_skill,
                skill_name=non_existent_skill,
                normalized_key="nonexistentskillmaster999",
                score=0.95
            )
        ]
        
        # Verify validate candidates filters it out because it doesn't exist in DB
        res = resolver._validate_candidates(
            input_skill="some skill",
            normalized_skill="some skill",
            candidates=candidates
        )
        self.assertFalse(res.accepted)

    def test_zero_job_description_dependency(self):
        # Verify that get_skill_gap_report does not query or load Job Description DocType at runtime.
        # We will mock frappe.db.get_value, frappe.db.get_all, frappe.db.exists, and frappe.get_doc,
        # and if any of them is called with "Job Description", we raise an error.
        
        student_id = "test_zero_jd_student@example.com"
        college_name = frappe.db.get_value("College", {}, "name") or "Default College"
        
        # Setup test student
        if not frappe.db.exists("Student", student_id):
            stu = frappe.get_doc({
                "doctype": "Student",
                "first_name": "Test",
                "last_name": "Zero",
                "email_id": student_id,
                "college": college_name
            })
            stu.insert(ignore_permissions=True)
        
        career_name = "Machine Learning Engineer"
        if not frappe.db.exists("Career Knowledge", {"career_name": career_name}):
            ck = frappe.get_doc({
                "doctype": "Career Knowledge",
                "career_name": career_name,
                "active": 1
            })
            ck.insert(ignore_permissions=True)
            
        frappe.db.commit()
        
        # Spy/Block "Job Description" DocType access
        orig_get_doc = frappe.get_doc
        orig_get_all = frappe.get_all
        orig_get_value = frappe.db.get_value
        orig_exists = frappe.db.exists
        
        def mock_get_doc(*args, **kwargs):
            if args and args[0] == "Job Description":
                raise AssertionError("Runtime accessed 'Job Description' DocType via get_doc!")
            if kwargs.get("doctype") == "Job Description":
                raise AssertionError("Runtime accessed 'Job Description' DocType via get_doc!")
            return orig_get_doc(*args, **kwargs)
            
        def mock_get_all(*args, **kwargs):
            if args and args[0] == "Job Description":
                raise AssertionError("Runtime accessed 'Job Description' DocType via get_all!")
            return orig_get_all(*args, **kwargs)
            
        def mock_get_value(*args, **kwargs):
            if args and args[0] == "Job Description":
                raise AssertionError("Runtime accessed 'Job Description' DocType via get_value!")
            return orig_get_value(*args, **kwargs)
            
        def mock_exists(*args, **kwargs):
            if args and args[0] == "Job Description":
                raise AssertionError("Runtime accessed 'Job Description' DocType via exists!")
            if len(args) > 1 and args[1] == "Job Description":
                raise AssertionError("Runtime accessed 'Job Description' DocType via exists!")
            return orig_exists(*args, **kwargs)
            
        from unittest.mock import patch
        
        with patch("frappe.get_doc", side_effect=mock_get_doc), \
             patch("frappe.get_all", side_effect=mock_get_all), \
             patch("frappe.db.get_value", side_effect=mock_get_value), \
             patch("frappe.db.exists", side_effect=mock_exists):
             
             service = SkillGapService()
             # We pass a dict profile to bypass real LLM calls and Qdrant cache checks during test
             career_profile = {
                 "role_name": "Machine Learning Engineer",
                 "foundation_skills": ["Python"],
                 "core_domain_skills": ["Machine Learning"],
                 "industry_skills": [],
                 "emerging_skills": []
             }
             report = service.get_skill_gap_report(student=student_id, career=career_profile)
             
             self.assertEqual(report.career, "Machine Learning Engineer")
             
        # Cleanup
        frappe.db.delete("Student", {"name": student_id})
        frappe.db.commit()

    def test_skill_agent_cache_validation_and_contamination(self):
        import requests
        from job_search_ai.agents.skill_agent.knowledge_cache import SkillKnowledgeCache
        from job_search_ai.agents.skill_agent.schemas import SkillProfile, SkillRequest
        from job_search_ai.services.settings_service import SettingsService
        from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
        from job_search_ai.agents.skill_agent.validator import validate_and_normalize_profile
        from unittest.mock import patch, MagicMock

        settings = SettingsService.get()
        cache = SkillKnowledgeCache(settings)

        # 1. Test invalid/exceeding limits cached Frontend profile is rejected and causes a rebuild
        bad_frontend_payload = {
            "role_name": "Frontend Developer",
            "foundation_skills": ["HTML", "CSS", "JavaScript"],
            # 10 skills, limit is 8
            "core_domain_skills": ["React", "Redux", "TypeScript", "Webpack", "Vite", "HTML5", "CSS3", "LESS", "SASS", "Stylus"],
            "industry_skills": ["Responsive Web Design"],
            "emerging_skills": ["AI-assisted development"],
            "schema_version": "v4"
        }

        original_post = requests.post

        qdrant_search_response = {
            "result": [
                {
                    "id": "mock-hit-id-123",
                    "score": 0.95,
                    "payload": bad_frontend_payload
                }
            ]
        }

        mock_post_calls = []
        def mock_qdrant_post(url, *args, **kwargs):
            mock_post_calls.append((url, kwargs.get("json")))
            if "points/search" in url:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = qdrant_search_response
                return mock_resp
            if "points/delete" in url:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"result": {"status": "completed"}}
                return mock_resp
            return original_post(url, *args, **kwargs)

        with patch("requests.post", side_effect=mock_qdrant_post), \
             patch("requests.get") as mock_get:
            
            mock_get.return_value.status_code = 200
            profile = cache.lookup("Frontend Developer")
            
            self.assertIsNone(profile)
            
            delete_calls = [url for url, json_body in mock_post_calls if "points/delete" in url]
            self.assertEqual(len(delete_calls), 1)

        # 2. Test DevOps/Backend contamination in Frontend Developer cache
        contaminated_frontend_payload = {
            "role_name": "Frontend Developer",
            "foundation_skills": ["HTML", "CSS", "JavaScript"],
            "core_domain_skills": ["React", "Express.js"],  # Express.js is a blocked backend skill!
            "industry_skills": [],
            "emerging_skills": [],
            "schema_version": "v4"
        }

        qdrant_search_response = {
            "result": [
                {
                    "id": "mock-hit-id-456",
                    "score": 0.95,
                    "payload": contaminated_frontend_payload
                }
            ]
        }

        mock_post_calls.clear()
        with patch("requests.post", side_effect=mock_qdrant_post):
            profile = cache.lookup("Frontend Developer")
            self.assertIsNone(profile)
            delete_calls = [url for url, json_body in mock_post_calls if "points/delete" in url]
            self.assertEqual(len(delete_calls), 1)

        # 3. Test valid cached profile remains a 0-LLM HIT
        valid_frontend_payload = {
            "role_name": "Frontend Developer",
            "foundation_skills": ["HTML5", "JavaScript", "Git"],
            "core_domain_skills": ["ReactJS"],
            "industry_skills": [],
            "emerging_skills": [],
            "schema_version": "v4"
        }

        qdrant_search_response = {
            "result": [
                {
                    "id": "mock-hit-id-789",
                    "score": 0.99,
                    "payload": valid_frontend_payload
                }
            ]
        }

        mock_post_calls.clear()
        with patch("requests.post", side_effect=mock_qdrant_post):
            profile = cache.lookup("Frontend Developer")
            self.assertIsNotNone(profile)
            self.assertEqual(profile.role_name, "Frontend Developer")
            delete_calls = [url for url, json_body in mock_post_calls if "points/delete" in url]
            self.assertEqual(len(delete_calls), 0)

        # 4. Test Career Fit Validation: AI Engineer cannot accept frontend-only profile
        invalid_ai_profile = SkillProfile(
            role_name="AI Engineer",
            foundation_skills=["HTML", "CSS", "JavaScript"],
            core_domain_skills=["React", "Redux", "TypeScript"],
            industry_skills=[],
            emerging_skills=[]
        )
        with self.assertRaises(ValueError) as ctx:
            validate_and_normalize_profile(invalid_ai_profile)
        self.assertIn("career fit score", str(ctx.exception).lower())

        # 5. Test Career Fit Validation: Frappe Developer cannot accept frontend-only profile
        invalid_frappe_profile = SkillProfile(
            role_name="Frappe Developer",
            foundation_skills=["HTML", "CSS", "JavaScript"],
            core_domain_skills=["React", "Redux", "TypeScript"],
            industry_skills=[],
            emerging_skills=[]
        )
        with self.assertRaises(ValueError) as ctx:
            validate_and_normalize_profile(invalid_frappe_profile)
        self.assertIn("career fit score", str(ctx.exception).lower())

        # 6. Test Career Fit Validation: DevOps cannot accept frontend contamination
        invalid_devops_profile = SkillProfile(
            role_name="DevOps Engineer",
            foundation_skills=["Git"],
            core_domain_skills=["ReactJS", "typescript"],  # Frontend contamination
            industry_skills=[],
            emerging_skills=[]
        )
        with self.assertRaises(ValueError) as ctx:
            validate_and_normalize_profile(invalid_devops_profile)
        self.assertIn("career fit score", str(ctx.exception).lower())

        # 7. Test regenerated profile respects all limits and is not silently truncated
        agent = SkillAgent()
        
        attempt_calls = []
        def mock_generate_skills(role, seniority=None, feedback=None):
            attempt_calls.append(role)
            if len(attempt_calls) == 1:
                return {
                    "role": role,
                    "foundation_skills": ["Python", "SQL", "Git"],
                    "core_domain_skills": ["Machine Learning", "TensorFlow", "PyTorch", "Deep Learning", "Neural Networks"],
                    "industry_skills": ["Pandas", "NumPy"],
                    "emerging_skills": ["LangGraph", "Wasm", "WebAssembly", "Quantum", "VR"]
                }
            else:
                return {
                    "role": role,
                    "foundation_skills": ["Python", "SQL", "Git"],
                    "core_domain_skills": ["Machine Learning", "TensorFlow", "PyTorch", "Deep Learning", "Neural Networks"],
                    "industry_skills": ["Pandas", "NumPy"],
                    "emerging_skills": ["Generative AI"]
                }

        with patch("job_search_ai.agents.skill_agent.llm_service.LLMService.generate_skills", side_effect=mock_generate_skills), \
             patch.object(SkillKnowledgeCache, "lookup", return_value=None), \
             patch.object(SkillKnowledgeCache, "store") as mock_store:
            
            res = agent.run(SkillRequest(role="AI Engineer"), save_to_doctype=False)
            
            self.assertEqual(len(attempt_calls), 2)
            self.assertEqual(len(res.profile.emerging_skills), 1)
            self.assertEqual(res.profile.emerging_skills[0], "Generative AI")


def run_tests():
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRemediations)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        import sys
        sys.exit(1)


def run_career_trend():
    from job_search_ai.services.career_trend_service import CareerTrendService
    import json
    try:
        res = CareerTrendService.get_trends(
            degree="Engineering",
            branch="Computer Engineering",
            year=1,
            country="India",
            interests="Frappe",
            skills="ErpNext, Frappe,Python"
        )
        print("RESULT:")
        print(json.dumps(res, indent=2))
    except Exception as exc:
        print("ERROR:", exc)
        import traceback
        traceback.print_exc()




