"""
Diagnose empty recommendations for STU057 (Ritesh Engineering to Finance)
"""
import sys
import logging
import json
import frappe

logging.basicConfig(level=logging.INFO)

def run():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    from job_search_ai.agents.career_trend.agent import CareerTrendAgent
    from job_search_ai.agents.career_trend.schemas import StudentProfile
    from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine
    from unittest.mock import patch
    import hashlib
    import numpy as np
    from groq import Groq

    api_key = frappe.conf.get("groq_api_key")
    if not api_key:
        raise RuntimeError("groq_api_key not set")
    groq_client = Groq(api_key=api_key)

    def mock_groq(*args, **kwargs):
        prompt = next((a for a in args if isinstance(a, str)), kwargs.get("prompt", ""))
        try:
            r = groq_client.chat.completions.create(
                model="groq/compound-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=30,
            )
            return r.choices[0].message.content or "{}"
        except Exception:
            return "{}"

    def mock_embed(self, text):
        h = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(h, "big") % (2 ** 32)
        rng = np.random.default_rng(seed)
        v = rng.uniform(-1.0, 1.0, 768)
        v /= np.linalg.norm(v)
        return v.tolist()

    patches = [
        patch("job_search_ai.agents.career_trend.llm_service.LLMService._call_llm", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_openai_compat", mock_groq),
        patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed", mock_embed),
    ]
    for p in patches:
        p.start()

    # STU057
    student = StudentProfile(
        degree="B.Tech",
        branch="Mechanical Engineering",
        year=3,
        country="India",
        interests=["Finance", "Investment Banking", "Financial Modeling"],
        skills=["Excel", "Financial Modeling", "Valuation", "Python"]
    )

    from job_search_ai.services.settings_service import SettingsService
    settings = SettingsService.get()
    agent = CareerTrendAgent()

    # 1. Retrieve candidates
    from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
    retriever = KnowledgeRetriever(settings=settings)
    retrieved = retriever.retrieve(student)
    print(f"\nRetrieved {len(retrieved)} candidates from DB:")
    for r in retrieved:
        print(f"  - {r.career_name} (similarity={getattr(r, 'similarity', None)})")

    # 2. Score candidates
    engine = RecommendationEngine()
    scored = engine.rank(student, retrieved)
    print(f"\nScored {len(scored)} candidates:")
    for sc in scored:
        print(f"  - {sc.candidate.career_name}: final_score={sc.final_score:.4f}, fit_type={engine._classify_fit(student, sc.candidate).value}")

    # 3. Full agent run
    try:
        resp = agent.run(student)
        print("\nAgent recommendations:")
        for r in resp.recommended_paths:
            print(f"  - {r.career} ({r.confidence}%) - {getattr(r, 'scores', {}).get('fit_type', 'N/A')}")
        if not resp.recommended_paths:
            print("\nAgent returned EMPTY recommendations.")
    except Exception as e:
        print(f"\nAgent run failed: {e}")

if __name__ == "__main__":
    run()
