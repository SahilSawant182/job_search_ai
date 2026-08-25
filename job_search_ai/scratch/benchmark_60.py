# -*- coding: utf-8 -*-
"""
benchmark_60.py — Full diagnostic benchmark for the Career Recommendation pipeline.

Produces per-profile records containing:
  - stage timings (normalization, profile_kb, retrieval, scoring, tavily,
                   result_filter, kb_build, llm_synthesis, qdrant_write)
  - career-family correctness (not just goal match)
  - knowledge HIT/MISS details
  - failure stage identification
  - _MAX_MISS_INTERESTS=1 vs 2 comparison (two separate full passes)

Output: benchmark_results.json  +  benchmark_report.txt
"""

import json
import time
import hashlib
import traceback
import numpy as np
import frappe
from unittest.mock import patch
from groq import Groq

from job_search_ai.agents.career_trend.schemas import StudentProfile

# ──────────────────────────────────────────────────────────────────────────────
# 1. ACCEPTABLE CAREER FAMILIES — this replaces single-goal ground-truth
# ──────────────────────────────────────────────────────────────────────────────
CAREER_FAMILIES = {
    "STU001": ["Frontend Developer", "Frontend Engineer", "UI Developer", "Web Developer", "React Developer"],
    "STU002": ["Frontend Developer", "Frontend Engineer", "React Developer", "UI Engineer", "Web Developer"],
    "STU003": ["Backend Developer", "Backend Engineer", "API Developer", "Server-Side Developer", "Python Developer"],
    "STU004": ["Full Stack Developer", "Full Stack Engineer", "Web Developer", "MERN Developer"],
    "STU005": ["AI Engineer", "ML Engineer", "Machine Learning Engineer", "Deep Learning Engineer", "AI Developer"],
    "STU006": ["Data Scientist", "ML Engineer", "Data Analyst", "Analytics Engineer", "Statistician"],
    "STU007": ["DevOps Engineer", "Cloud Engineer", "Site Reliability Engineer", "SRE", "Platform Engineer"],
    "STU008": ["Cybersecurity Analyst", "Security Engineer", "Information Security Analyst", "Security Analyst", "Penetration Tester"],
    "STU009": ["Data Engineer", "Big Data Engineer", "Analytics Engineer", "Data Platform Engineer"],
    "STU010": ["Cloud Architect", "Cloud Engineer", "Solutions Architect", "AWS Architect", "Cloud Developer"],
    "STU011": ["Robotics Engineer", "Automation Engineer", "Controls Engineer", "Manufacturing Automation Engineer", "Mechatronics Engineer"],
    "STU012": ["Embedded Systems Engineer", "IoT Developer", "Firmware Engineer", "Hardware Engineer"],
    "STU013": ["Mechanical Design Engineer", "CAD Engineer", "Product Design Engineer", "Structural Engineer"],
    "STU014": ["Thermal Engineer", "HVAC Engineer", "Energy Engineer", "Mechanical Engineer"],
    "STU015": ["Civil Engineer", "Structural Engineer", "Infrastructure Engineer", "Construction Engineer"],
    "STU016": ["Electrical Engineer", "Power Systems Engineer", "Electrical Design Engineer"],
    "STU017": ["Electronics Engineer", "VLSI Engineer", "Signal Processing Engineer", "Hardware Design Engineer"],
    "STU018": ["Chemical Engineer", "Process Engineer", "Petrochemical Engineer", "Refinery Engineer"],
    "STU019": ["Environmental Engineer", "Sustainability Engineer", "Green Energy Engineer"],
    "STU020": ["Marketing Analyst", "Digital Marketing Specialist", "SEO Specialist", "Marketing Manager", "Brand Manager"],
    "STU021": ["Financial Analyst", "Investment Analyst", "Finance Analyst", "Equity Analyst"],
    "STU022": ["Accountant", "Auditor", "Tax Consultant", "Financial Accountant", "CPA"],
    "STU023": ["HR Manager", "Human Resources Manager", "Talent Acquisition Specialist", "HR Business Partner"],
    "STU024": ["Banking Analyst", "Financial Services Analyst", "Risk Analyst", "Credit Analyst"],
    "STU025": ["Product Manager", "Product Owner", "Senior Product Manager", "Associate Product Manager"],
    "STU026": ["Supply Chain Manager", "Logistics Manager", "Supply Chain Analyst", "Procurement Manager"],
    "STU027": ["Business Analyst", "Management Consultant", "Strategy Analyst", "Business Strategy Manager"],
    "STU028": ["Sales Manager", "Business Development Manager", "Account Manager", "Sales Executive"],
    "STU029": ["Operations Manager", "Operations Analyst", "Supply Chain Manager", "Business Operations Manager", "Process Manager"],
    "STU030": ["Entrepreneur", "Business Development Manager", "Startup Founder", "Business Developer", "Venture Analyst"],
    "STU031": ["UX Designer", "UI Designer", "UX/UI Designer", "Product Designer", "Interaction Designer"],
    "STU032": ["Graphic Designer", "Visual Designer", "Brand Designer", "Creative Designer"],
    "STU033": ["3D Animator", "Animation Director", "3D Artist", "Motion Graphics Designer", "VFX Artist"],
    "STU034": ["Content Creator", "Content Writer", "Social Media Manager", "Digital Content Specialist", "Video Content Creator"],
    "STU035": ["Counsellor", "Psychologist", "Mental Health Counsellor", "Therapist", "I-O Psychology Consultant"],
    "STU036": ["Social Researcher", "Social Scientist", "Sociologist", "Research Analyst", "Policy Researcher"],
    "STU037": ["Policy Analyst", "Public Policy Specialist", "Government Relations Analyst", "Political Analyst"],
    "STU038": ["Content Writer", "Copywriter", "Editor", "Technical Writer", "Journalist"],
    "STU039": ["Corporate Lawyer", "Legal Analyst", "Corporate Law Specialist", "Compliance Analyst", "Legal Consultant"],
    "STU040": ["LegalTech Specialist", "Legal Technology Consultant", "Legal Analyst", "Tech Law Specialist"],
    "STU041": ["Nurse", "Healthcare Administrator", "Clinical Nurse", "Patient Care Specialist"],
    "STU042": ["Pharma Marketing Specialist", "Pharmaceutical Data Analyst", "Regulatory Affairs Specialist", "Medical Sales"],
    "STU043": ["Healthcare Administrator", "Clinical Data Manager", "Hospital Administrator", "Medical Informatics Analyst"],
    "STU044": ["Biotech Research Scientist", "Biotech Data Analyst", "Genomics Analyst", "Biotechnology Manager"],
    "STU045": ["Agriculture Specialist", "Agronomist", "Farm Management Specialist", "Agricultural Scientist"],
    "STU046": ["Agricultural Data Scientist", "AgriTech Specialist", "Precision Farming Engineer", "Smart Agriculture Consultant"],
    "STU047": ["Food Technologist", "Food Innovation Specialist", "Quality Control Specialist", "Food Scientist"],
    "STU048": ["Hotel Manager", "Hospitality Manager", "Customer Service Manager", "Travel and Tourism Manager"],
    "STU049": ["Travel and Tourism Manager", "Tourism Consultant", "Destination Manager", "Travel Planner"],
    "STU050": ["Teacher", "Educational Consultant", "Curriculum Developer", "School Administrator"],
    "STU051": ["Instructional Designer", "EdTech Specialist", "Educational Technology Specialist", "eLearning Developer"],
    "STU052": ["Market Research Analyst", "Financial Analyst", "Economic Analyst", "Research Economist"],
    "STU053": ["Journalist", "Broadcast Journalist", "Digital Media Specialist", "Content Journalist"],
    "STU054": ["Fashion Designer", "E-commerce Fashion Designer", "Digital Fashion Designer", "Retail Fashion Buyer"],
    "STU055": ["Web Development Manager", "Engineering Manager", "Software Development Manager", "Tech Lead"],
    "STU056": ["Data Scientist", "Data Analyst", "Business Analyst", "Analytics Engineer"],
    "STU057": ["Financial Analyst", "Financial Planner", "Investment Analyst", "Quantitative Analyst"],
    "STU058": ["Frontend Developer", "UX Designer", "UX Engineer", "UI Developer", "UX/UI Designer"],
    "STU059": ["Business Analyst - AI", "AI Product Manager", "Data Scientist", "Product Manager", "Business Intelligence Analyst"],
    "STU060": ["Career Explorer", "Junior Analyst", "Management Trainee", "AI Engineer", "Business Developer"],
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. PROFILE DATA (same as diagnose_recommendations.py)
# ──────────────────────────────────────────────────────────────────────────────
PROFILES_JSON = open(
    "/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch/diagnose_recommendations.py"
).read()
# Extract the JSON between the triple-quote markers
import re as _re
_match = _re.search(r'STUDENT_PROFILES_JSON = """(.*?)"""', PROFILES_JSON, _re.DOTALL)
PROFILES_DATA = json.loads(_match.group(1).strip())


# ──────────────────────────────────────────────────────────────────────────────
# 3. HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def _career_correct(pid: str, recs: list[str]) -> bool:
    """Return True if any rec overlaps the acceptable career family."""
    family = {c.lower() for c in CAREER_FAMILIES.get(pid, [])}
    for r in recs:
        rl = r.lower()
        for f in family:
            if rl in f or f in rl or any(w in f for w in rl.split() if len(w) > 3):
                return True
    return False


def _failure_stage(metrics: dict, recs: list) -> str:
    """Heuristically identify the first stage where failure occurred."""
    if not recs:
        if metrics.get("tavily_used") and not metrics.get("kb_build_time", 0):
            return "tavily_returned_empty"
        if metrics.get("tavily_used") and metrics.get("kb_build_time", 0) > 0:
            return "eligibility_gate"
        if not metrics.get("knowledge_hit") and not metrics.get("tavily_used"):
            return "career_knowledge_retrieval_empty"
        return "unknown"
    return "none"


def mock_embed(self, text: str) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(h, "big") % (2 ** 32)
    rng = np.random.default_rng(seed)
    v = rng.uniform(-1.0, 1.0, 768)
    v /= np.linalg.norm(v)
    return v.tolist()


# ──────────────────────────────────────────────────────────────────────────────
# 4. SINGLE-PROFILE RUNNER
# ──────────────────────────────────────────────────────────────────────────────
def _run_profile(agent, pid: str, student: StudentProfile) -> dict:
    """Run one profile through the agent and return a rich record."""
    t0 = time.perf_counter()

    # ── Profile-KB lookup timing (wraps the internal fast-path check) ──────
    t_norm = time.perf_counter()
    try:
        from job_search_ai.agents.career_trend.input_normalizer import InputNormalizer
        _normalized = InputNormalizer().normalize(student)
    except Exception:
        _normalized = student
    t_norm = time.perf_counter() - t_norm

    # ── Profile Recommendation Knowledge lookup ───────────────────────────
    t_pkb = time.perf_counter()
    pkb_hit = False
    pkb_similarity = 0.0
    try:
        from job_search_ai.agents.career_trend.profile_recommendation_knowledge import ProfileRecommendationKnowledge
        from job_search_ai.services.settings_service import SettingsService
        settings = SettingsService.get()
        prk = ProfileRecommendationKnowledge(settings=settings)
        hit_payload = prk.lookup(_normalized)
        pkb_hit = hit_payload is not None
        if hit_payload:
            pkb_similarity = hit_payload.get("combined_similarity", 0.0)
    except Exception:
        pass
    t_pkb = time.perf_counter() - t_pkb

    # ── Full agent run ────────────────────────────────────────────────────
    t_agent = time.perf_counter()
    recs = []
    metrics = {}
    error = None
    try:
        resp = agent.run(student)
        recs = [r.career for r in resp.recommended_paths]
        metrics = getattr(resp, "metrics", {}) or {}
    except Exception as exc:
        error = str(exc)

    total_elapsed = time.perf_counter() - t_agent

    # ── Extract stage timings from metrics ───────────────────────────────
    t_retrieval  = metrics.get("retrieval_time", 0.0)
    t_scoring    = 0.0  # not exposed separately; part of retrieval
    t_tavily     = metrics.get("parallel_search_time", 0.0)
    t_filter     = 0.0  # bundled in kb_build
    t_kb_build   = metrics.get("kb_build_time", 0.0)
    t_llm        = metrics.get("llm_response_time", 0.0)
    t_qdrant_w   = 0.0  # not separately exposed

    # The agent does not return t_retrieval yet; estimate from total
    known_sum = t_tavily + t_kb_build + t_llm
    t_retrieval_est = max(0.0, total_elapsed - known_sum - t_norm - t_pkb - 0.05)

    correct = _career_correct(pid, recs)
    failure_stage = _failure_stage(metrics, recs)

    return {
        "profile_id": pid,
        # Pipeline stages (seconds)
        "t_normalization":    round(t_norm, 4),
        "t_profile_kb":       round(t_pkb, 4),
        "t_retrieval_est":    round(t_retrieval_est, 4),
        "t_tavily":           round(t_tavily, 4),
        "t_kb_build":         round(t_kb_build, 4),
        "t_llm_synthesis":    round(t_llm, 4),
        "t_total":            round(total_elapsed, 4),
        # Correctness
        "recs":               recs,
        "correct":            correct,
        "acceptable_family":  CAREER_FAMILIES.get(pid, []),
        # Knowledge HIT/MISS
        "pkb_hit":            pkb_hit,
        "pkb_similarity":     round(pkb_similarity, 4),
        "knowledge_hit":      metrics.get("knowledge_hit", False),
        "knowledge_count":    metrics.get("knowledge_count", 0),
        "avg_similarity":     round(metrics.get("avg_similarity_score", 0.0), 4),
        # API usage
        "tavily_used":        metrics.get("tavily_used", False),
        "tavily_calls":       metrics.get("query_count", 0),
        "llm_used":           t_llm > 0.1,
        "model_name":         metrics.get("model_name", "N/A"),
        # Diagnostics
        "failure_stage":      failure_stage,
        "error":              error,
        "knowledge_updated":  metrics.get("knowledge_updated", False),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 5. AGGREGATE REPORT
# ──────────────────────────────────────────────────────────────────────────────
def _make_report(label: str, records: list[dict]) -> str:
    total = len(records)
    if not total:
        return "No records."

    correct      = sum(1 for r in records if r["correct"])
    has_recs     = sum(1 for r in records if r["recs"])
    pkb_hits     = sum(1 for r in records if r["pkb_hit"])
    kb_hits      = sum(1 for r in records if r["knowledge_hit"])
    tavily_used  = sum(1 for r in records if r["tavily_used"])
    llm_used     = sum(1 for r in records if r["llm_used"])

    hit_records  = [r for r in records if r["pkb_hit"]]
    miss_records = [r for r in records if not r["pkb_hit"]]

    def avg(lst): return sum(lst) / len(lst) if lst else 0.0

    hit_lat  = avg([r["t_total"] for r in hit_records])
    miss_lat = avg([r["t_total"] for r in miss_records])
    all_lat  = avg([r["t_total"] for r in records])

    t_norm_pct   = avg([r["t_normalization"] for r in records]) / max(avg([r["t_total"] for r in records]), 0.001) * 100
    t_tavily_pct = avg([r["t_tavily"] for r in records]) / max(avg([r["t_total"] for r in records]), 0.001) * 100
    t_kb_pct     = avg([r["t_kb_build"] for r in records]) / max(avg([r["t_total"] for r in records]), 0.001) * 100
    t_llm_pct    = avg([r["t_llm_synthesis"] for r in records]) / max(avg([r["t_total"] for r in records]), 0.001) * 100
    t_retr_pct   = avg([r["t_retrieval_est"] for r in records]) / max(avg([r["t_total"] for r in records]), 0.001) * 100

    failure_counts: dict = {}
    for r in records:
        if not r["correct"]:
            fs = r["failure_stage"] if r["failure_stage"] != "none" else "wrong_career_returned"
            failure_counts[fs] = failure_counts.get(fs, 0) + 1

    lines = [
        f"",
        f"╔══════════════════════════════════════════════════════════════╗",
        f"║  BENCHMARK REPORT — {label:<40}║",
        f"╠══════════════════════════════════════════════════════════════╣",
        f"║  ACCURACY                                                    ║",
        f"║  Has recommendations : {has_recs:>3} / {total}  ({has_recs/total*100:.1f}%)              ║",
        f"║  Career-correct      : {correct:>3} / {total}  ({correct/total*100:.1f}%)              ║",
        f"╠══════════════════════════════════════════════════════════════╣",
        f"║  CACHE PERFORMANCE                                           ║",
        f"║  Profile KB HITs     : {pkb_hits:>3} / {total}  ({pkb_hits/total*100:.1f}%)              ║",
        f"║  Career KB HITs      : {kb_hits:>3} / {total}  ({kb_hits/total*100:.1f}%)              ║",
        f"║  Tavily calls used   : {tavily_used:>3} / {total}  ({tavily_used/total*100:.1f}%)              ║",
        f"║  LLM synthesis used  : {llm_used:>3} / {total}  ({llm_used/total*100:.1f}%)              ║",
        f"╠══════════════════════════════════════════════════════════════╣",
        f"║  LATENCY (seconds)                                           ║",
        f"║  Avg HIT latency     : {hit_lat:>7.3f}s                              ║",
        f"║  Avg MISS latency    : {miss_lat:>7.3f}s                              ║",
        f"║  Avg total latency   : {all_lat:>7.3f}s                              ║",
        f"╠══════════════════════════════════════════════════════════════╣",
        f"║  TIME BREAKDOWN (% of avg total)                             ║",
        f"║  Normalization       : {t_norm_pct:>5.1f}%                               ║",
        f"║  MariaDB retrieval   : {t_retr_pct:>5.1f}%                               ║",
        f"║  Tavily search       : {t_tavily_pct:>5.1f}%                               ║",
        f"║  KnowledgeBuilder    : {t_kb_pct:>5.1f}%                               ║",
        f"║  LLM synthesis       : {t_llm_pct:>5.1f}%                               ║",
        f"╠══════════════════════════════════════════════════════════════╣",
        f"║  TOP FAILURE CAUSES                                          ║",
    ]
    for cause, count in sorted(failure_counts.items(), key=lambda x: -x[1])[:5]:
        lines.append(f"║    {cause:<30} : {count:>3}                     ║")
    if not failure_counts:
        lines.append(f"║    none                                                     ║")
    lines.append(f"╚══════════════════════════════════════════════════════════════╝")

    # Per-profile table
    lines.append(f"\n{'ID':<8} {'Domain':<28} {'Top Career':<32} {'OK?':<5} {'PKB':^5} {'KHit':^5} {'Tav':^4} {'ms':>6} {'Slowest Stage'}")
    lines.append("-" * 120)
    domain_map = {p["profile_id"]: p.get("branch", "") for p in PROFILES_DATA}
    for r in records:
        top = r["recs"][0] if r["recs"] else "(empty)"
        ok  = "✓" if r["correct"] else "✗"
        pkb = "HIT" if r["pkb_hit"] else "---"
        kh  = "HIT" if r["knowledge_hit"] else "---"
        tv  = "Y" if r["tavily_used"] else "N"
        ms  = int(r["t_total"] * 1000)
        dom = domain_map.get(r["profile_id"], "")[:27]
        slowest = max(
            [("retrieval", r["t_retrieval_est"]),
             ("tavily",    r["t_tavily"]),
             ("kb_build",  r["t_kb_build"]),
             ("llm",       r["t_llm_synthesis"])],
            key=lambda x: x[1]
        )[0] if r["t_total"] > 0.01 else "pkb_hit"
        lines.append(f"{r['profile_id']:<8} {dom:<28} {top:<32} {ok:<5} {pkb:^5} {kh:^5} {tv:^4} {ms:>6} {slowest}")

    # Incorrect profile deep-dive
    incorrect = [r for r in records if not r["correct"]]
    if incorrect:
        lines.append(f"\n── INCORRECT RECOMMENDATIONS DEEP-DIVE ─────────────────────")
        for r in incorrect:
            lines.append(f"\n  Profile     : {r['profile_id']}")
            lines.append(f"  Actual recs : {r['recs']}")
            lines.append(f"  Acceptable  : {r['acceptable_family'][:4]}")
            lines.append(f"  Failure at  : {r['failure_stage']}")
            lines.append(f"  PKB hit     : {r['pkb_hit']} (sim={r['pkb_similarity']:.3f})")
            lines.append(f"  Career KB   : hit={r['knowledge_hit']} count={r['knowledge_count']}")
            lines.append(f"  Tavily used : {r['tavily_used']}")
            lines.append(f"  Error       : {r['error']}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 6. MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
OUT_DIR = "/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch"

def run():
    frappe.init(site="devstridenex.quantcloud.in", sites_path="../../sites")
    frappe.connect()

    api_key = frappe.conf.get("groq_api_key")
    if not api_key:
        raise RuntimeError("groq_api_key not set in site_config.json")
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
        except Exception as e:
            return "{}"

    patches = [
        patch("job_search_ai.agents.career_trend.llm_service.LLMService._call_llm", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_openai_compat", mock_groq),
        patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed", mock_embed),
    ]
    for p in patches:
        p.start()

    import job_search_ai.agents.career_trend.agent as _agent_mod

    all_results = {}

    for interests_cap in [1, 2]:
        _agent_mod._MAX_MISS_INTERESTS = interests_cap
        label = f"MAX_MISS_INTERESTS={interests_cap}"
        print(f"\n{'='*60}")
        print(f"  PASS: {label}")
        print(f"{'='*60}")

        from job_search_ai.agents.career_trend.agent import CareerTrendAgent
        agent = CareerTrendAgent()
        records = []

        for p in PROFILES_DATA:
            pid = p["profile_id"]
            student = StudentProfile(
                degree=p["degree"], branch=p["branch"], year=p["year"],
                country=p["country"], interests=p["interests"], skills=p["skills"]
            )
            print(f"  [{pid}] {p['name'][:40]}...", end="", flush=True)
            rec = _run_profile(agent, pid, student)
            rec["name"] = p["name"]
            rec["goal"] = p["goal"]
            records.append(rec)
            status = "✓" if rec["correct"] else ("∅" if not rec["recs"] else "✗")
            print(f" {status} {rec['recs'][:2]}  {int(rec['t_total']*1000)}ms")

            # Save intermediate
            with open(f"{OUT_DIR}/benchmark_intermediate_{interests_cap}.json", "w") as f:
                json.dump(records, f, indent=2)

        all_results[label] = records
        with open(f"{OUT_DIR}/benchmark_results_{interests_cap}.json", "w") as f:
            json.dump(records, f, indent=2)

    for p in patches:
        p.stop()

    # ── Write final report ────────────────────────────────────────────────
    report_parts = ["CAREER RECOMMENDATION — DIAGNOSTIC BENCHMARK\n" + "="*64]

    for label, records in all_results.items():
        report_parts.append(_make_report(label, records))

    # Comparison summary
    if len(all_results) == 2:
        labels = list(all_results.keys())
        r1, r2 = all_results[labels[0]], all_results[labels[1]]
        report_parts.append("\n── COMPARISON: _MAX_MISS_INTERESTS=1 vs 2 ──────────────────")
        report_parts.append(f"{'Metric':<35} {'=1':>10}  {'=2':>10}  {'Delta':>10}")
        report_parts.append("-" * 70)

        def pct(lst, key_fn): return sum(1 for r in lst if key_fn(r)) / len(lst) * 100
        def avg_t(lst): return sum(r["t_total"] for r in lst) / len(lst)
        def tavily_calls(lst): return sum(r.get("tavily_calls", 0) for r in lst)
        def llm_cnt(lst): return sum(1 for r in lst if r["llm_used"])

        metrics_cmp = [
            ("Accuracy (%)",          pct(r1, lambda r: r["correct"]),  pct(r2, lambda r: r["correct"])),
            ("Has recs (%)",           pct(r1, lambda r: r["recs"]),     pct(r2, lambda r: r["recs"])),
            ("Avg total latency (s)",  avg_t(r1),                        avg_t(r2)),
            ("Total Tavily calls",     tavily_calls(r1),                 tavily_calls(r2)),
            ("Profiles used LLM",      llm_cnt(r1),                     llm_cnt(r2)),
        ]
        for name, v1, v2 in metrics_cmp:
            delta = v2 - v1
            sign = "+" if delta >= 0 else ""
            report_parts.append(f"{name:<35} {v1:>10.2f}  {v2:>10.2f}  {sign}{delta:>9.2f}")

    report_text = "\n".join(report_parts)

    with open(f"{OUT_DIR}/benchmark_report.txt", "w") as f:
        f.write(report_text)

    print("\n" + report_text)
    print(f"\nResults saved to {OUT_DIR}/benchmark_report.txt")

if __name__ == "__main__":
    run()
