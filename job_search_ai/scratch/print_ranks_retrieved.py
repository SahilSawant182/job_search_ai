# -*- coding: utf-8 -*-
import sys
import frappe
sys.path.append("/home/dev/frappe-bench/apps/job_search_ai")

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    from job_search_ai.agents.career_trend.schemas import StudentProfile
    from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine
    from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
    from job_search_ai.services.settings_service import SettingsService
    from unittest.mock import patch
    import hashlib
    import numpy as np

    def mock_embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode('utf-8')).digest()
        seed = int.from_bytes(h, 'big') % (2**32)
        rng = np.random.default_rng(seed)
        v = rng.uniform(-1.0, 1.0, 768)
        v /= np.linalg.norm(v)
        return v.tolist()

    p_emb = patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed", mock_embed)
    p_emb.start()

    try:
        student = StudentProfile(
            degree="B.Tech",
            branch="Computer Science",
            year=2,
            country="India",
            interests=["Frontend Development", "Web Development", "UI Development"],
            skills=["HTML", "CSS", "JavaScript"]
        )
        
        settings = SettingsService.get()
        retriever = KnowledgeRetriever(settings=settings)
        
        # Test fallback_name_match directly
        print("Testing fallback_name_match...")
        matching = retriever._fallback_name_match(student, settings.similarity_threshold or 0.6)
        print("Fallback matches:", [r.career_name for r in matching])
        
        retrieved = retriever.retrieve(student)
        
        print("Number of retrieved candidates:", len(retrieved))
        for r in retrieved:
            print(f"Retrieved: {r.career_name} | similarity: {r.similarity:.4f} | req_skills: {r.required_skills} | pref_skills: {r.preferred_skills}")
            
        engine = RecommendationEngine()
        scored = engine.rank(student, retrieved)
        print("\nNumber of scored candidates:", len(scored))
        for sc in scored:
            print(f"Scored Career: {sc.candidate.career_name} | Score: {sc.final_score:.4f} | Skills match: {sc.scores['skill_match']:.4f} | Interest match: {sc.scores['interest_match']:.4f}")
    finally:
        p_emb.stop()

if __name__ == "__main__":
    run()
