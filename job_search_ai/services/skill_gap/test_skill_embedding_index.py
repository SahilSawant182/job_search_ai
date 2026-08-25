"""
Unit tests for persistent skill embedding index infrastructure.
Run via:
python -m unittest job_search_ai.services.skill_gap.test_skill_embedding_index
"""

import unittest

from job_search_ai.services.skill_gap.matcher import SemanticSkillMatcher
from job_search_ai.services.skill_gap.skill_embedding_index import (
    PersistentSkillEmbeddingCache,
    SkillEmbeddingBuilder,
    SkillEmbeddingIndex,
    SkillEmbeddingResolver,
    SkillIndexConfig,
    SkillMasterRecord,
    SkillSearchCandidate,
    build_skill_embedding_text,
)


class FakeHit:
    def __init__(self, id, score, payload):
        self.id = id
        self.score = score
        self.payload = payload


class FakeVectorIndex:
    def __init__(self, hits=None):
        self.hits = hits or []
        self.created = 0
        self.upserts = []
        self.searches = []
        self.deletes = []

    def create_collection(self, *, recreate=False):
        self.created += 1
        return True

    def upsert(self, id, vector, payload=None):
        self.upserts.append((id, vector, payload or {}))

    def delete(self, id):
        self.deletes.append(id)

    def search(self, query_vector, limit=10, score_threshold=None):
        self.searches.append((query_vector, limit, score_threshold))
        return self.hits[:limit]


class FakeRepository:
    def __init__(self, records):
        self.records = {record.skill_id: record for record in records}

    def get_active_skills(self):
        return [record for record in self.records.values() if record.active]

    def get_skill(self, skill_id):
        return self.records.get(skill_id)

    def find_active_by_key(self, skill_name):
        key = skill_name.lower().replace(".", "").strip()
        for record in self.get_active_skills():
            if record.normalized_key == key:
                return record
            if any(alias.lower().replace(".", "").strip() == key for alias in record.aliases):
                return record
        return None


class TestSkillEmbeddingIndex(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.patcher = patch("job_search_ai.services.skill_gap.skill_embedding_index._get_frappe", return_value=None)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_rich_embedding_text_uses_skill_master_fields(self):
        record = SkillMasterRecord(
            skill_id="Python",
            skill_name="Python",
            normalized_key="python",
            aliases=["Python Programming", "Core Python"],
            category="Programming Language",
            domain="Software Engineering",
            description="General purpose programming language.",
        )

        text = build_skill_embedding_text(record)

        self.assertIn("Skill Name: Python", text)
        self.assertIn("Aliases: Python Programming, Core Python", text)
        self.assertIn("Category: Programming Language", text)
        self.assertIn("Domain: Software Engineering", text)
        self.assertIn("Description: General purpose programming language.", text)

    def test_persistent_cache_reuses_vector_for_same_model_version_and_hash(self):
        cache = PersistentSkillEmbeddingCache(memory_store={})
        cache.set("python", "Skill Name: Python", [1.0, 2.0], "model-a", "v1", "hash-a")

        self.assertEqual(cache.get("python", "model-a", "v1", "hash-a"), [1.0, 2.0])
        self.assertIsNone(cache.get("python", "model-b", "v1", "hash-a"))
        self.assertIsNone(cache.get("python", "model-a", "v2", "hash-a"))
        self.assertIsNone(cache.get("python", "model-a", "v1", "hash-b"))

    def test_builder_uses_cache_and_upserts_skill_payload_to_qdrant(self):
        calls = []

        def embed(text):
            calls.append(text)
            return [0.1, 0.2]

        record = SkillMasterRecord(
            skill_id="Python",
            skill_name="Python",
            normalized_key="python",
            aliases=["Core Python"],
            category="Language",
            domain="Software",
            description="General purpose language.",
        )
        vector_index = FakeVectorIndex()
        builder = SkillEmbeddingBuilder(
            embedding_provider=embed,
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=vector_index, config=SkillIndexConfig()),
            repository=FakeRepository([record]),
            embedding_model="model-a",
            config=SkillIndexConfig(embedding_version="v1"),
        )

        builder.sync_record(record)
        builder.sync_record(record)

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(vector_index.upserts), 2)
        payload = vector_index.upserts[0][2]
        self.assertEqual(payload["skill_master_id"], "Python")
        self.assertEqual(payload["skill_name"], "Python")
        self.assertEqual(payload["normalized_key"], "python")
        self.assertEqual(payload["aliases"], ["Core Python"])
        self.assertEqual(payload["embedding_model"], "model-a")
        self.assertEqual(payload["embedding_version"], "v1")

    def test_resolver_accepts_high_confidence_with_sufficient_gap(self):
        hits = [
            FakeHit("Python", 0.95, {"skill_master_id": "Python", "skill_name": "Python", "normalized_key": "python", "active": True}),
            FakeHit("Java", 0.60, {"skill_master_id": "Java", "skill_name": "Java", "normalized_key": "java", "active": True}),
        ]
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=FakeVectorIndex(hits), config=SkillIndexConfig()),
            repository=FakeRepository([]),
            config=SkillIndexConfig(auto_match_threshold=0.90, uncertain_threshold=0.75, confidence_gap_threshold=0.05),
            embedding_model="model-a",
        )

        result = resolver.resolve("Python Programming")

        self.assertTrue(result.accepted)
        self.assertEqual(result.canonical_skill, "Python")
        self.assertEqual(result.stage, "qdrant_high_confidence")

    def test_resolver_rejects_ambiguous_confidence_gap(self):
        hits = [
            FakeHit("Python", 0.91, {"skill_master_id": "Python", "skill_name": "Python", "normalized_key": "python", "active": True}),
            FakeHit("Python Scripting", 0.89, {"skill_master_id": "Python Scripting", "skill_name": "Python Scripting", "normalized_key": "python scripting", "active": True}),
        ]
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=FakeVectorIndex(hits), config=SkillIndexConfig()),
            repository=FakeRepository([]),
            config=SkillIndexConfig(auto_match_threshold=0.90, uncertain_threshold=0.75, confidence_gap_threshold=0.05),
            embedding_model="model-a",
        )

        result = resolver.resolve("Python Automation")

        self.assertFalse(result.accepted)
        self.assertEqual(result.confidence_band, "uncertain")
        self.assertEqual(result.fallback_reason, "ambiguous_confidence_gap")

    def test_resolver_rejects_inactive_candidate(self):
        hits = [FakeHit("OldSkill", 0.96, {"skill_master_id": "OldSkill", "skill_name": "OldSkill", "normalized_key": "oldskill", "active": False})]
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=FakeVectorIndex(hits), config=SkillIndexConfig()),
            repository=FakeRepository([]),
            config=SkillIndexConfig(),
            embedding_model="model-a",
        )

        result = resolver.resolve("Old Skill")

        self.assertFalse(result.accepted)
        self.assertEqual(result.fallback_reason, "inactive_candidate")

    def test_resolver_uses_llm_only_for_uncertain_candidates(self):
        hits = [FakeHit("Python", 0.84, {"skill_master_id": "Python", "skill_name": "Python", "normalized_key": "python", "active": True})]
        llm_calls = []
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=FakeVectorIndex(hits), config=SkillIndexConfig()),
            repository=FakeRepository([]),
            config=SkillIndexConfig(auto_match_threshold=0.90, uncertain_threshold=0.75),
            embedding_model="model-a",
        )

        result = resolver.resolve("Python Automation", llm_decider=lambda left, right: llm_calls.append((left, right)) or True)

        self.assertTrue(result.accepted)
        self.assertEqual(result.stage, "llm_fallback")
        self.assertEqual(llm_calls, [("Python Automation", "Python")])

    def test_matcher_can_match_through_persistent_resolver(self):
        hits = [FakeHit("Data Visualization", 0.95, {"skill_master_id": "Data Visualization", "skill_name": "Data Visualization", "normalized_key": "data visualization", "active": True})]
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=FakeVectorIndex(hits), config=SkillIndexConfig()),
            repository=FakeRepository([]),
            config=SkillIndexConfig(auto_match_threshold=0.90),
            embedding_model="model-a",
        )
        matcher = SemanticSkillMatcher(skill_resolver=resolver)

        matches = matcher.match_skills(["Charting"], ["Data Visualization"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].stage, "semantic_index")
        self.assertEqual(matches[0].canonical_skill, "Data Visualization")

    def test_resolver_exact_alias_match_does_not_embed_or_search(self):
        record = SkillMasterRecord(
            skill_id="Python",
            skill_name="Python",
            normalized_key="python",
            aliases=["Core Python"],
            active=True,
        )
        calls = []
        vector_index = FakeVectorIndex()
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: calls.append(text) or [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=vector_index, config=SkillIndexConfig()),
            repository=FakeRepository([record]),
            config=SkillIndexConfig(),
            embedding_model="model-a",
        )

        result = resolver.resolve("Core Python")

        self.assertTrue(result.accepted)
        self.assertEqual(result.canonical_skill, "Python")
        self.assertEqual(result.stage, "skill_master_exact")
        self.assertEqual(calls, [])
        self.assertEqual(vector_index.searches, [])

    def test_resolver_uses_configured_top_k_for_qdrant_lookup(self):
        vector_index = FakeVectorIndex([
            FakeHit("Python", 0.95, {"skill_master_id": "Python", "skill_name": "Python", "normalized_key": "python", "active": True})
        ])
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=vector_index, config=SkillIndexConfig(top_k=3)),
            repository=FakeRepository([]),
            config=SkillIndexConfig(top_k=3),
            embedding_model="model-a",
        )

        resolver.resolve("Python Automation")

        self.assertEqual(vector_index.searches[0][1], 3)

    def test_unknown_skill_returns_candidate_decision_without_active_skill_creation(self):
        resolver = SkillEmbeddingResolver(
            embedding_provider=lambda text: [1.0, 0.0],
            cache=PersistentSkillEmbeddingCache(memory_store={}),
            index=SkillEmbeddingIndex(vector_index=FakeVectorIndex([]), config=SkillIndexConfig()),
            repository=FakeRepository([]),
            config=SkillIndexConfig(),
            embedding_model="model-a",
        )

        result = resolver.resolve("LangGraph")

        self.assertFalse(result.accepted)
        self.assertIsNone(result.canonical_skill)
        self.assertEqual(result.stage, "unknown")
        self.assertEqual(result.fallback_reason, "no_candidates")


if __name__ == "__main__":
    unittest.main()
