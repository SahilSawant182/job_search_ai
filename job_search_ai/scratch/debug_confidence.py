# -*- coding: utf-8 -*-
import sys
import json
import hashlib
import numpy as np
import frappe
from unittest.mock import patch
from groq import Groq

sys.path.append("/home/dev/frappe-bench/apps/job_search_ai")

from job_search_ai.agents.career_trend.agent import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile

def run_debug():
    frappe.init(site="devstridenex.quantcloud.in")
    frappe.connect()

    api_key = frappe.conf.get("groq_api_key")
    groq_client = Groq(api_key=api_key)

    def mock_execute_groq(*args, **kwargs):
        prompt = ""
        if args:
            for arg in args:
                if isinstance(arg, str):
                    prompt = arg
                    break
        if not prompt and "prompt" in kwargs:
            prompt = kwargs["prompt"]
        try:
            response = groq_client.chat.completions.create(
                model="groq/compound-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=30,
            )
            return response.choices[0].message.content or "{}"
        except Exception as exc:
            print(f"Mock Groq Exception: {exc}")
            return "{}"

    def mock_embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode('utf-8')).digest()
        seed = int.from_bytes(h, 'big') % (2**32)
        rng = np.random.default_rng(seed)
        v = rng.uniform(-1.0, 1.0, 768)
        v /= np.linalg.norm(v)
        return v.tolist()

    p_llm = patch("job_search_ai.agents.career_trend.llm_service.LLMService._call_llm", mock_execute_groq)
    p_kb = patch("job_search_ai.services.skill_gap.knowledge_builder.SkillKnowledgeBuilder._execute_llm", mock_execute_groq)
    p_ext = patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama", mock_execute_groq)
    p_ext_open = patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_openai_compat", mock_execute_groq)
    p_emb = patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed", mock_embed)

    p_llm.start()
    p_kb.start()
    p_ext.start()
    p_ext_open.start()
    p_emb.start()

    try:
        agent = CareerTrendAgent()
        student = StudentProfile(
            degree="B.Tech",
            branch="Computer Science",
            year=2,
            country="India",
            interests=["Frontend Development", "Web Development", "UI Development"],
            skills=["HTML", "CSS", "JavaScript"]
        )
        print("Running CareerTrendAgent for STU001...")
        resp = agent.run(student)
        print(f"Strategy: {resp.strategy}")
        print("Recommended paths:")
        for r in resp.recommended_paths:
            print(f"  Career: {r.career} | Confidence: {r.confidence} | Why: {r.why_for_you}")
        print(f"Metrics: {getattr(resp, 'metrics', {})}")
    finally:
        p_llm.stop()
        p_kb.stop()
        p_ext.stop()
        p_ext_open.stop()
        p_emb.stop()

if __name__ == "__main__":
    run_debug()
