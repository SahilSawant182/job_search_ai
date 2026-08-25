import json
import re
import frappe
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.agents.career_trend.agent import CareerTrendAgent
from job_search_ai.agents.career_trend.profile_recommendation_knowledge import ProfileRecommendationKnowledge
from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine
from job_search_ai.services.settings_service import SettingsService
from unittest.mock import patch
import hashlib
import numpy as np
from groq import Groq

# Mock functions
def mock_embed(self, text):
    h = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(h, "big") % (2 ** 32)
    rng = np.random.default_rng(seed)
    v = rng.uniform(-1.0, 1.0, 768)
    v /= np.linalg.norm(v)
    return v.tolist()

# Load profiles
_diag = open("/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch/diagnose_recommendations.py").read()
_m = re.search(r'STUDENT_PROFILES_JSON = """(.*?)"""', _diag, re.DOTALL)
PROFILES_DATA = json.loads(_m.group(1).strip())

TARGET_PIDS = ["STU001", "STU018", "STU019", "STU022", "STU030", "STU040", "STU041", "STU055", "STU059"]

def trace_profile(p, bypass_cache):
    pid = p["profile_id"]
    print(f"==================================================")
    print(f"TRACING {pid} - {p['name']} ({'COLD' if bypass_cache else 'WARM'})")
    print(f"==================================================")
    
    settings = SettingsService.get()
    rec_knowledge = ProfileRecommendationKnowledge(settings)
    engine = RecommendationEngine()
    agent = CareerTrendAgent()
    
    student = StudentProfile(
        degree=p["degree"], branch=p["branch"], year=p["year"],
        country=p["country"], interests=p["interests"], skills=p["skills"]
    )
    
    # 1. PKB lookup details
    hit_payload = rec_knowledge.lookup(student)
    pkb_hit = (hit_payload is not None) and (not bypass_cache)
    pkb_sim = 0.0
    pkb_domain_compat = "N/A"
    
    if hit_payload:
        pkb_sim = hit_payload.get("combined_similarity", 0.0)
        from job_search_ai.agents.career_trend.profile_recommendation_knowledge import _classify_domain, _domains_compatible
        student_domain = _classify_domain(student.branch, student.degree)
        cached_domain = hit_payload.get("academic_domain", "unknown")
        pkb_domain_compat = "Compatible" if _domains_compatible(student_domain, cached_domain) else "Incompatible"
        
    print(f"PKB Hit/Miss       : {'HIT' if pkb_hit else 'MISS'}")
    print(f"PKB Similarity     : {pkb_sim:.4f}")
    print(f"Domain Compat      : {pkb_domain_compat}")
    
    # 2. Retrieve candidates list
    from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
    retriever = KnowledgeRetriever(settings)
    retrieved = retriever.retrieve(student)
    print(f"Candidate Count    : {len(retrieved)}")
    print(f"Candidate Careers  : {[r.career_name for r in retrieved]}")
    
    # 3. Recommendation engine scoring
    scored = engine.rank(student, retrieved) if retrieved else []
    print(f"Scored Candidates count: {len(scored)}")
    
    # Let's run the agent to get LLM response
    recs_after_llm = []
    try:
        if bypass_cache:
            with patch("job_search_ai.agents.career_trend.profile_recommendation_knowledge.ProfileRecommendationKnowledge.lookup", return_value=None):
                resp = agent.run(student)
        else:
            resp = agent.run(student)
        recs_after_llm = [r.career for r in resp.recommended_paths]
    except Exception as e:
        print(f"Agent Run Exception: {e}")
        
    python_rank = [sc.candidate.career_name for sc in scored]
    print(f"Python Rank (Pre-LLM): {python_rank[:3]}")
    print(f"LLM Rank (Post-LLM)  : {recs_after_llm[:3]}")
    
    changed = False
    if python_rank and recs_after_llm:
        if python_rank[0].lower().strip() != recs_after_llm[0].lower().strip():
            changed = True
    print(f"LLM Changed Rank?  : {'YES' if changed else 'NO'}")
    
    print("\nTop Scored Candidates Details:")
    for i, sc in enumerate(scored[:3]):
        cand = sc.candidate
        print(f"  {i+1}. {cand.career_name}:")
        print(f"     Interest Score : {sc.scores.get('interest_match', 0.0):.4f}")
        print(f"     Skill Score    : {sc.scores.get('skill_match', 0.0):.4f}")
        print(f"     Degree Score   : {sc.scores.get('degree_match', 0.0):.4f}")
        print(f"     Branch Score   : {sc.scores.get('branch_match', 0.0):.4f}")
        print(f"     Fit Type       : {sc.scores.get('fit_type', 'N/A')}")
        print(f"     Final Score    : {sc.final_score:.4f}")
        print(f"     Reason Codes   : {sc.reason_codes}")
    print("-" * 50)

def main():
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

    patches = [
        patch("job_search_ai.agents.career_trend.llm_service.LLMService._call_llm", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_openai_compat", mock_groq),
        patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed", mock_embed),
    ]
    for p in patches:
        p.start()

    for pid in TARGET_PIDS:
        p = [x for x in PROFILES_DATA if x["profile_id"] == pid][0]
        # Trace cold cache first
        trace_profile(p, bypass_cache=True)
        # Trace warm cache second
        trace_profile(p, bypass_cache=False)

    for p in patches:
        p.stop()

if __name__ == "__main__":
    main()
